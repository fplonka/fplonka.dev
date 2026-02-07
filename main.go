package main

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
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

	http.HandleFunc("/organize-anything", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "./static/organize-anything/skeleton.html")
	})
	http.HandleFunc("/fragment/", serveFragment)

	http.ListenAndServe(":3001", nil)
}

// Handler to serve fragment files
func serveFragment(w http.ResponseWriter, r *http.Request) {
	fragmentID := filepath.Base(r.URL.Path)
	filename := filepath.Join("static/organize-anything/", fragmentID+".html")

	fmt.Println("WANT:", fragmentID)

	if _, err := os.Stat(filename); os.IsNotExist(err) {
		http.NotFound(w, r)
		fmt.Println("not found...")
		return
	}

	http.ServeFile(w, r, filename)
}
