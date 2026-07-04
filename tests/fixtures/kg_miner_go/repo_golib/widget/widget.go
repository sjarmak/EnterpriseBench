package widget

import (
	"example.com/gobase/core"
	"example.com/golibstats"
)

// NewWidget builds a widget description from a core Thing.
func NewWidget(name string) string {
	t := core.NewThing(name)
	golibstats.Count()
	return core.Describe(t)
}

// Describe returns a static description.
func Describe() string {
	return "widget"
}
