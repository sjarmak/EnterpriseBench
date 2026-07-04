package core

// Thing is the base domain object.
type Thing struct {
	Name string
}

// NewThing constructs a Thing.
func NewThing(name string) Thing {
	return Thing{Name: name}
}

// Describe renders a Thing.
func Describe(t Thing) string {
	return "thing:" + t.Name
}
