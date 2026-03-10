package main

import (
	"fmt"
	"strings" // used in production code
)

func greet(name string) string {
	return fmt.Sprintf("Hello, %s!", name)
}

func (s *Server) handleRequest(req Request) Response {
	return Response{Status: 200}
}

type Server struct {
	Host string
	Port int
}

type Request struct {
	Path string
}

type Response struct {
	Status int
}
