package main

import (
	"fmt"

	// aliased cross-repo import
	w "example.com/golib/widget"

	"example.com/goapp/internal/config"
)

func main() {
	cfg := config.Load()
	fmt.Println(w.NewWidget(cfg.Name))
	fmt.Println(w.Describe())
}
