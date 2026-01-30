//go:build linux || darwin

package main

import (
	"os"

	"golang.org/x/sys/unix"
)

func mmapFile(file *os.File, size int) ([]byte, error) {
	return unix.Mmap(int(file.Fd()), 0, size, unix.PROT_READ|unix.PROT_WRITE, unix.MAP_SHARED)
}

func munmapFile(b []byte) error {
	return unix.Munmap(b)
}
