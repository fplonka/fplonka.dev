package main

import (
	"fmt"
	"net/http"
)

func hello(w http.ResponseWriter, req *http.Request) {

	fmt.Fprintf(w, "hello\n")
}

func main() {

	http.Handle("/", http.FileServer(http.Dir("./static")))

	http.ListenAndServe(":8080", nil)
}
