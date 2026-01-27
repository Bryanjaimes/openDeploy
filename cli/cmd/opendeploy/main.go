package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
)

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	switch os.Args[1] {
	case "run":
		runCmd(os.Args[2:])
	default:
		printUsage()
		os.Exit(1)
	}
}

func runCmd(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	apiKey := fs.String("api-key", "secret-key-123", "API key for local requests")
	_ = fs.Parse(args)

	rest := fs.Args()
	if len(rest) < 1 {
		fmt.Fprintln(os.Stderr, "missing model name")
		printUsage()
		os.Exit(1)
	}
	model := rest[0]

	if err := runDockerCompose(); err != nil {
		fmt.Fprintf(os.Stderr, "failed to start services: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("✅ OpenDeploy local runner is up")
	fmt.Printf("Model: %s\n", model)
	fmt.Println("Endpoint: http://localhost:8000/generate")
	fmt.Printf("API Key: %s\n", *apiKey)
}

func runDockerCompose() error {
	if err := execDockerCompose("docker", []string{"compose", "up", "-d", "--build", "api"}); err == nil {
		return nil
	}
	if err := execDockerCompose("docker-compose", []string{"up", "-d", "--build", "api"}); err == nil {
		return nil
	}
	return errors.New("docker compose not available")
}

func execDockerCompose(cmd string, args []string) error {
	c := exec.Command(cmd, args...)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin
	return c.Run()
}

func printUsage() {
	fmt.Println("OpenDeploy CLI (V0)")
	fmt.Println("Usage:")
	fmt.Println("  opendeploy run <model> [--api-key <key>]")
	fmt.Println("")
	fmt.Println("Example:")
	fmt.Println("  opendeploy run tiny-llama-chat")
}
