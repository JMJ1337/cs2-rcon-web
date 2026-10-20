//go:build windows

package main

import (
	"syscall"
	"time"
	"unsafe"
)

var (
	user32            = syscall.NewLazyDLL("user32.dll")
	procFindWindow    = user32.NewProc("FindWindowW")
	procSetForeground = user32.NewProc("SetForegroundWindow")
	procShowWindow    = user32.NewProc("ShowWindow")
	procKeybdEvent    = user32.NewProc("keybd_event")
)

const vkPause = 0x13

// CS2-Fenster nach vorne holen und die Pause-Taste drücken (dort liegt per Bind „exec grohlan_tv“)
func pressBind() bool {
	title, _ := syscall.UTF16PtrFromString("Counter-Strike 2")
	h, _, _ := procFindWindow.Call(0, uintptr(unsafe.Pointer(title)))
	if h != 0 {
		procShowWindow.Call(h, 9) // SW_RESTORE
		procSetForeground.Call(h)
		time.Sleep(400 * time.Millisecond)
	}
	procKeybdEvent.Call(vkPause, 0x45, 0, 0)
	time.Sleep(60 * time.Millisecond)
	procKeybdEvent.Call(vkPause, 0x45, 2, 0) // KEYEVENTF_KEYUP
	return h != 0
}
