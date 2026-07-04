package widget

import "example.com/gobase/core"

// Test files must be excluded from the mined graph entirely.
func helperForTest() string {
	return core.Describe(core.NewThing("t"))
}
