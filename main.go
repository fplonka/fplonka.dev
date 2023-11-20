package main

import (
	"net/http"
)

func main() {

	http.Handle("/", http.FileServer(http.Dir("./static")))

	http.HandleFunc("/bpfreq", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "./static/bpfreq.html")
	})

	http.HandleFunc("/go-llca", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "./static/go-llca.html")
	})

	http.ListenAndServe(":3001", nil)
}
