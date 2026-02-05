package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"time"

	"github.com/spf13/cobra"
)

func newRunCmd() *cobra.Command {
	var (
		apiKey          string
		runner          string
		strategy        string
		region          string
		instanceType    string
		maxPrice        float64
		onDemandPrice   float64
		lookbackMinutes int
		provider        string
	)

	cmd := &cobra.Command{
		Use:   "run <model>",
		Short: "Start a local model runner",
		Long: `Starts a Docker Compose stack serving the specified model via the
API runner (FastAPI) or vLLM runner. Optionally queries spot pricing
before launch when --strategy cheapest is set.`,
		Example: `  opendeploy run tiny-llama-chat
  opendeploy run TinyLlama/TinyLlama-1.1B-Chat-v1.0 --runner vllm
  opendeploy run tiny-llama-chat --strategy cheapest --region us-east-1 --instance-type g5.xlarge --max-price 1.00`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			model := args[0]

			if strategy == "cheapest" {
				lookback := time.Duration(lookbackMinutes) * time.Minute
				if err := printScheduleRecommendation(provider, region, instanceType, maxPrice, onDemandPrice, lookback); err != nil {
					return fmt.Errorf("scheduling failed: %w", err)
				}
			}

			if err := runDockerCompose(runner, model); err != nil {
				return fmt.Errorf("failed to start services: %w", err)
			}

			fmt.Println("✅ OpenDeploy local runner is up")
			fmt.Printf("Model: %s\n", model)
			if runner == "vllm" {
				fmt.Println("Endpoint: http://localhost:8001/v1/chat/completions")
				fmt.Println("Note: vLLM is OpenAI-compatible; no API key required by default")
			} else {
				fmt.Println("Endpoint: http://localhost:8000/generate")
				fmt.Printf("API Key: %s\n", apiKey)
			}
			return nil
		},
	}

	cmd.Flags().StringVar(&apiKey, "api-key", "secret-key-123", "API key for local requests")
	cmd.Flags().StringVar(&runner, "runner", "api", "Runner backend: api | vllm")
	cmd.Flags().StringVar(&strategy, "strategy", "", "Scheduling strategy (e.g. cheapest)")
	cmd.Flags().StringVar(&region, "region", "us-east-1", "Cloud region for scheduling")
	cmd.Flags().StringVar(&instanceType, "instance-type", "g5.xlarge", "Instance type for scheduling")
	cmd.Flags().Float64Var(&maxPrice, "max-price", 0, "Max USD/hr for spot (0 = no limit)")
	cmd.Flags().Float64Var(&onDemandPrice, "on-demand-price", 0, "On-demand USD/hr for savings estimate")
	cmd.Flags().IntVar(&lookbackMinutes, "lookback-minutes", 60, "Spot price lookback window (minutes)")
	cmd.Flags().StringVar(&provider, "provider", "aws", "Cloud provider: aws | gcp | all")

	return cmd
}

// ---------------------------------------------------------------------------
// Docker Compose helpers
// ---------------------------------------------------------------------------

func runDockerCompose(runner, model string) error {
	if runner == "vllm" {
		env := append(os.Environ(), fmt.Sprintf("VLLM_MODEL=%s", model))
		if err := execDockerComposeWithEnv("docker", []string{"compose", "-f", "docker-compose.vllm.yml", "up", "-d", "vllm"}, env); err == nil {
			return nil
		}
		if err := execDockerComposeWithEnv("docker-compose", []string{"-f", "docker-compose.vllm.yml", "up", "-d", "vllm"}, env); err == nil {
			return nil
		}
		return errors.New("docker compose not available")
	}

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

func execDockerComposeWithEnv(cmd string, args []string, env []string) error {
	c := exec.Command(cmd, args...)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin
	c.Env = env
	return c.Run()
}
