package main

import (
	"net/http"
)

func main() {

	http.Handle("/", http.FileServer(http.Dir("./static")))

	http.HandleFunc("/bpfreq", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "./static/bpfreq/bpfreq.html")
	})

	http.HandleFunc("/go-llca", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "./static/go-llca/go-llca.html")
	})

	http.HandleFunc("/git-cluster", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "./static/git-cluster/git-cluster.html")
	})

	// Serve files from git-cluster/output
	http.Handle("/git-cluster/output/", http.StripPrefix("/git-cluster/output/", http.FileServer(http.Dir("./static/git-cluster/output"))))

	http.ListenAndServe(":3001", nil)
}
