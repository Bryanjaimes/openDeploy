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
	shmSize := envOrDefaultInt("OPENDEPLOY_SHM_SIZE", 16*1024*1024)
	defaultWidth := envOrDefaultInt("FRAME_WIDTH", 0)
	defaultHeight := envOrDefaultInt("FRAME_HEIGHT", 0)
	defaultFormat := envOrDefaultInt("FRAME_FORMAT", formatRGB)
	maxWidth := envOrDefaultInt("OPENDEPLOY_MAX_FRAME_WIDTH", 1920)
	maxHeight := envOrDefaultInt("OPENDEPLOY_MAX_FRAME_HEIGHT", 1080)
	maxBytes := envOrDefaultInt("OPENDEPLOY_MAX_FRAME_BYTES", 4*1920*1080)
	apiKey := strings.TrimSpace(os.Getenv("OPENDEPLOY_API_KEY"))
	allowedOrigins := parseAllowedOrigins(os.Getenv("OPENDEPLOY_ALLOWED_ORIGINS"))

	writer, err := NewShmWriter(shmPath, shmSize)
	if err != nil {
		log.Fatalf("failed to init shm writer: %v", err)
	}
	defer writer.Close()

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

type ShmWriter struct {
	path   string
	size   int
	mmap   []byte
	seq    uint64
	closed atomic.Bool
}

func NewShmWriter(path string, size int) (*ShmWriter, error) {
	file, err := os.OpenFile(path, os.O_RDWR|os.O_CREATE, 0600)
	if err != nil {
		return nil, err
	}
	if err := file.Truncate(int64(size)); err != nil {
		_ = file.Close()
		return nil, err
	}

	mmapData, err := mmapFile(file, size)
	if err != nil {
		_ = file.Close()
		return nil, err
	}

	_ = file.Close()

	writer := &ShmWriter{
		path: path,
		size: size,
		mmap: mmapData,
	}

	writer.resetHeader()
	return writer, nil
}

func (s *ShmWriter) WriteFrame(width, height, format uint32, payload []byte) error {
	if s.closed.Load() {
		return nil
	}

	payloadLen := len(payload)
	headerSize := shmHeaderSize()
	if headerSize+payloadLen > len(s.mmap) {
		return nil
	}

	seq := atomic.AddUint64(&s.seq, 1)
	ts := uint64(time.Now().UnixNano())

	copy(s.mmap[0:4], []byte("ODSH"))
	binary.LittleEndian.PutUint32(s.mmap[4:8], 1)
	binary.LittleEndian.PutUint32(s.mmap[8:12], width)
	binary.LittleEndian.PutUint32(s.mmap[12:16], height)
	binary.LittleEndian.PutUint32(s.mmap[16:20], format)
	binary.LittleEndian.PutUint32(s.mmap[20:24], uint32(payloadLen))
	binary.LittleEndian.PutUint64(s.mmap[24:32], seq)
	binary.LittleEndian.PutUint64(s.mmap[32:40], ts)
	copy(s.mmap[headerSize:headerSize+payloadLen], payload)

	return nil
}

func (s *ShmWriter) resetHeader() {
	if len(s.mmap) < shmHeaderSize() {
		return
	}
	copy(s.mmap[0:4], []byte("ODSH"))
	binary.LittleEndian.PutUint32(s.mmap[4:8], 1)
	binary.LittleEndian.PutUint32(s.mmap[8:12], 0)
	binary.LittleEndian.PutUint32(s.mmap[12:16], 0)
	binary.LittleEndian.PutUint32(s.mmap[16:20], 0)
	binary.LittleEndian.PutUint32(s.mmap[20:24], 0)
	binary.LittleEndian.PutUint64(s.mmap[24:32], 0)
	binary.LittleEndian.PutUint64(s.mmap[32:40], 0)
}

func (s *ShmWriter) Close() {
	if s.closed.Swap(true) {
		return
	}
	_ = munmapFile(s.mmap)
}

func shmHeaderSize() int {
	return 40
}
