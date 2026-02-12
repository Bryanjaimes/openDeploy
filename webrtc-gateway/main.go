package main

import (
	"encoding/binary"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/pion/webrtc/v3"
)

type offerRequest struct {
	SDP  string `json:"sdp"`
	Type string `json:"type"`
}

type answerResponse struct {
	SDP  string `json:"sdp"`
	Type string `json:"type"`
}

const (
	defaultHTTPAddr = ":7000"
	frameHeaderSize = 12
	formatRGB       = 1
	formatRGBA      = 2
	formatGRAY      = 3
)

func main() {
	addr := envOrDefault("WEBRTC_HTTP_ADDR", defaultHTTPAddr)
	shmPath := envOrDefault("OPENDEPLOY_SHM_PATH", "/dev/shm/opendeploy_frames")
	defaultWidth := envOrDefaultInt("FRAME_WIDTH", 0)
	defaultHeight := envOrDefaultInt("FRAME_HEIGHT", 0)
	defaultFormat := envOrDefaultInt("FRAME_FORMAT", formatRGB)
	maxWidth := envOrDefaultInt("OPENDEPLOY_MAX_FRAME_WIDTH", 1920)
	maxHeight := envOrDefaultInt("OPENDEPLOY_MAX_FRAME_HEIGHT", 1080)
	maxBytes := envOrDefaultInt("OPENDEPLOY_MAX_FRAME_BYTES", 4*1920*1080)
	ringSlots := envOrDefaultInt("OPENDEPLOY_RING_SLOTS", 64)
	apiKey := strings.TrimSpace(os.Getenv("OPENDEPLOY_API_KEY"))
	allowedOrigins := parseAllowedOrigins(os.Getenv("OPENDEPLOY_ALLOWED_ORIGINS"))

	writer, err := NewShmWriter(shmPath, ringSlots, maxBytes)
	if err != nil {
		log.Fatalf("failed to init shm writer: %v", err)
	}
	defer writer.Close()
	log.Printf("SHM ring buffer: %d slots, %d bytes/slot, %d MB total",
		ringSlots, maxBytes, writer.totalSize/(1024*1024))

	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	})

	http.HandleFunc("/offer", func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin != "" && isAllowedOrigin(origin, allowedOrigins) {
			w.Header().Set("Access-Control-Allow-Origin", origin)
		}
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		if apiKey != "" && r.Header.Get("X-API-Key") != apiKey {
			w.WriteHeader(http.StatusForbidden)
			return
		}

		var offer offerRequest
		if err := json.NewDecoder(r.Body).Decode(&offer); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}

		peerConnection, err := createPeerConnection()
		if err != nil {
			log.Printf("peer connection error: %v", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}

		peerConnection.OnDataChannel(func(dc *webrtc.DataChannel) {
			log.Printf("data channel: %s", dc.Label())
			dc.OnMessage(func(msg webrtc.DataChannelMessage) {
				if len(msg.Data) == 0 {
					return
				}

				width, height, format, payload := parseFrameMessage(msg.Data, defaultWidth, defaultHeight, defaultFormat, maxWidth, maxHeight, maxBytes)
				if width == 0 || height == 0 || len(payload) == 0 {
					return
				}

				if err := writer.WriteFrame(uint32(width), uint32(height), uint32(format), payload); err != nil {
					log.Printf("write frame error: %v", err)
				}
			})
		})

		peerConnection.OnTrack(func(track *webrtc.TrackRemote, receiver *webrtc.RTPReceiver) {
			log.Printf("track received: %s", track.Codec().MimeType)
			_ = receiver
			_ = track
			// Video track handling is intentionally omitted. Use a DataChannel to send raw frames.
		})

		if err := peerConnection.SetRemoteDescription(webrtc.SessionDescription{
			Type: webrtc.NewSDPType(offer.Type),
			SDP:  offer.SDP,
		}); err != nil {
			log.Printf("set remote description error: %v", err)
			w.WriteHeader(http.StatusBadRequest)
			return
		}

		answer, err := peerConnection.CreateAnswer(nil)
		if err != nil {
			log.Printf("create answer error: %v", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}

		gatherComplete := webrtc.GatheringCompletePromise(peerConnection)
		if err := peerConnection.SetLocalDescription(answer); err != nil {
			log.Printf("set local description error: %v", err)
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		<-gatherComplete

		resp := answerResponse{
			SDP:  peerConnection.LocalDescription().SDP,
			Type: peerConnection.LocalDescription().Type.String(),
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	})

	log.Printf("WebRTC gateway listening on %s", addr)
	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("http server error: %v", err)
	}
}

func createPeerConnection() (*webrtc.PeerConnection, error) {
	mediaEngine := &webrtc.MediaEngine{}
	if err := mediaEngine.RegisterDefaultCodecs(); err != nil {
		return nil, err
	}
	api := webrtc.NewAPI(webrtc.WithMediaEngine(mediaEngine))
	return api.NewPeerConnection(webrtc.Configuration{})
}

func parseFrameMessage(data []byte, defaultWidth, defaultHeight, defaultFormat, maxWidth, maxHeight, maxBytes int) (int, int, int, []byte) {
	if len(data) >= frameHeaderSize {
		width := int(binary.LittleEndian.Uint32(data[0:4]))
		height := int(binary.LittleEndian.Uint32(data[4:8]))
		format := int(binary.LittleEndian.Uint32(data[8:12]))
		payload := data[12:]
		if width > 0 && height > 0 && len(payload) > 0 {
			if width > maxWidth || height > maxHeight {
				return 0, 0, 0, nil
			}
			channels := channelsForFormat(format)
			if channels == 0 {
				return 0, 0, 0, nil
			}
			expected := width * height * channels
			if expected == 0 || len(payload) < expected || len(payload) > maxBytes {
				return 0, 0, 0, nil
			}
			return width, height, format, payload[:expected]
		}
	}

	if defaultWidth > 0 && defaultHeight > 0 {
		channels := channelsForFormat(defaultFormat)
		if channels == 0 {
			return 0, 0, 0, nil
		}
		expected := defaultWidth * defaultHeight * channels
		if expected == 0 || len(data) < expected || expected > maxBytes {
			return 0, 0, 0, nil
		}
		return defaultWidth, defaultHeight, defaultFormat, data[:expected]
	}

	return 0, 0, 0, nil
}

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func envOrDefaultInt(key string, fallback int) int {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func parseAllowedOrigins(value string) []string {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	parts := strings.Split(value, ",")
	allowed := make([]string, 0, len(parts))
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			allowed = append(allowed, trimmed)
		}
	}
	return allowed
}

func isAllowedOrigin(origin string, allowed []string) bool {
	if len(allowed) == 0 {
		return false
	}
	for _, entry := range allowed {
		if origin == entry {
			return true
		}
	}
	return false
}

func channelsForFormat(format int) int {
	switch format {
	case formatRGB:
		return 3
	case formatRGBA:
		return 4
	case formatGRAY:
		return 1
	default:
		return 0
	}
}

// ---------- ODSH v2 Ring Buffer Protocol ----------
//
// Global Header (64 bytes):
//   [0:4]   magic    = "ODSH"
//   [4:8]   version  = 2
//   [8:12]  num_slots
//   [12:16] slot_size           (slotHeaderSize + slot_data_capacity)
//   [16:24] write_seq (uint64)  monotonically increasing; slot = (write_seq-1) % num_slots
//   [24:28] slot_data_capacity  max payload bytes per slot
//   [28:64] reserved
//
// Per-Slot Header (40 bytes, repeats num_slots times starting at offset 64):
//   [0:4]   magic    = "ODSF"
//   [4:8]   width
//   [8:12]  height
//   [12:16] format   (1=RGB, 2=RGBA, 3=GRAY)
//   [16:20] data_len
//   [20:24] flags    (0=empty, 1=ready, 2=writing)
//   [24:32] seq      (uint64, matches global write_seq at write time)
//   [32:40] timestamp_ns (uint64)
//
// Slot Payload (slot_data_capacity bytes):
//   [40 .. 40+data_len)  raw pixel data

const (
	globalHeaderSize = 64
	slotHeaderSize   = 40
	slotFlagEmpty    = 0
	slotFlagReady    = 1
	slotFlagWriting  = 2
)

type ShmWriter struct {
	path         string
	totalSize    int
	numSlots     int
	slotSize     int
	slotCapacity int
	mmap         []byte
	seq          uint64
	closed       atomic.Bool
}

func NewShmWriter(path string, numSlots, slotCapacity int) (*ShmWriter, error) {
	slotSize := slotHeaderSize + slotCapacity
	totalSize := globalHeaderSize + numSlots*slotSize

	file, err := os.OpenFile(path, os.O_RDWR|os.O_CREATE, 0600)
	if err != nil {
		return nil, err
	}
	if err := file.Truncate(int64(totalSize)); err != nil {
		_ = file.Close()
		return nil, err
	}

	mmapData, err := mmapFile(file, totalSize)
	if err != nil {
		_ = file.Close()
		return nil, err
	}
	_ = file.Close()

	w := &ShmWriter{
		path:         path,
		totalSize:    totalSize,
		numSlots:     numSlots,
		slotSize:     slotSize,
		slotCapacity: slotCapacity,
		mmap:         mmapData,
	}
	w.initGlobalHeader()
	return w, nil
}

func (s *ShmWriter) initGlobalHeader() {
	for i := 0; i < globalHeaderSize; i++ {
		s.mmap[i] = 0
	}
	copy(s.mmap[0:4], []byte("ODSH"))
	binary.LittleEndian.PutUint32(s.mmap[4:8], 2) // version 2
	binary.LittleEndian.PutUint32(s.mmap[8:12], uint32(s.numSlots))
	binary.LittleEndian.PutUint32(s.mmap[12:16], uint32(s.slotSize))
	binary.LittleEndian.PutUint64(s.mmap[16:24], 0) // write_seq starts at 0
	binary.LittleEndian.PutUint32(s.mmap[24:28], uint32(s.slotCapacity))
}

func (s *ShmWriter) slotOffset(index int) int {
	return globalHeaderSize + index*s.slotSize
}

func (s *ShmWriter) WriteFrame(width, height, format uint32, payload []byte) error {
	if s.closed.Load() {
		return nil
	}

	payloadLen := len(payload)
	if payloadLen > s.slotCapacity {
		return nil
	}

	s.seq++
	slotIndex := int((s.seq - 1) % uint64(s.numSlots))
	off := s.slotOffset(slotIndex)
	h := s.mmap[off:]

	// Write slot header (flags = WRITING)
	copy(h[0:4], []byte("ODSF"))
	binary.LittleEndian.PutUint32(h[4:8], width)
	binary.LittleEndian.PutUint32(h[8:12], height)
	binary.LittleEndian.PutUint32(h[12:16], format)
	binary.LittleEndian.PutUint32(h[16:20], uint32(payloadLen))
	binary.LittleEndian.PutUint32(h[20:24], slotFlagWriting)
	binary.LittleEndian.PutUint64(h[24:32], s.seq)
	binary.LittleEndian.PutUint64(h[32:40], uint64(time.Now().UnixNano()))

	// Write payload
	copy(s.mmap[off+slotHeaderSize:off+slotHeaderSize+payloadLen], payload)

	// Mark slot as ready
	binary.LittleEndian.PutUint32(h[20:24], slotFlagReady)

	// Update global write_seq so readers see the latest slot
	binary.LittleEndian.PutUint64(s.mmap[16:24], s.seq)

	return nil
}

func (s *ShmWriter) Close() {
	if s.closed.Swap(true) {
		return
	}
	_ = munmapFile(s.mmap)
}
