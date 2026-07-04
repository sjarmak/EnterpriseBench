package report

import gw "example.com/golib/widget"

// Report renders a one-line widget report (single-form aliased import).
func Report() string {
	return gw.NewWidget("report")
}
