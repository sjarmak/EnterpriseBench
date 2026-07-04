package config

// Config holds app settings.
type Config struct {
	Name string
}

// Load returns the default config.
func Load() Config {
	return Config{Name: "fixture"}
}
