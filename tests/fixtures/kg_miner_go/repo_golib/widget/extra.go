package widget

import (
	_ "example.com/gobase/core" // blank import: side effects only, no binding
	. "strings"                 // dot import: no usable binding
)

// Upper exists so the dot import is used.
func Upper(s string) string {
	return ToUpper(s)
}
