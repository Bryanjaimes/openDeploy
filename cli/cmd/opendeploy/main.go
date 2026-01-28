package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"time"
)

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	switch os.Args[1] {
	case "run":
		runCmd(os.Args[2:])
	case "schedule":
		scheduleCmd(os.Args[2:])
	case "deploy":
		deployCmd(os.Args[2:])
	default:
		printUsage()
		os.Exit(1)
	}
}

func runCmd(args []string) {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	apiKey := fs.String("api-key", "secret-key-123", "API key for local requests")
	strategy := fs.String("strategy", "", "scheduling strategy (e.g., cheapest)")
	region := fs.String("region", "us-east-1", "AWS region for scheduling")
	instanceType := fs.String("instance-type", "g5.xlarge", "EC2 instance type for scheduling")
	maxPrice := fs.Float64("max-price", 0, "max USD per hour for spot (0 = no limit)")
	onDemandPrice := fs.Float64("on-demand-price", 0, "optional on-demand USD per hour for savings estimate")
	lookbackMinutes := fs.Int("lookback-minutes", 60, "lookback window in minutes for spot price history")
	_ = fs.Parse(args)

	rest := fs.Args()
	if len(rest) < 1 {
		fmt.Fprintln(os.Stderr, "missing model name")
		printUsage()
		os.Exit(1)
	}
	model := rest[0]

	if *strategy == "cheapest" {
		if err := printScheduleRecommendation(*region, *instanceType, *maxPrice, *onDemandPrice, time.Duration(*lookbackMinutes)*time.Minute); err != nil {
			fmt.Fprintf(os.Stderr, "scheduling failed: %v\n", err)
			os.Exit(1)
		}
	}

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

func deployCmd(args []string) {
	fs := flag.NewFlagSet("deploy", flag.ExitOnError)
	cloud := fs.String("cloud", "aws", "cloud provider (aws)")
	region := fs.String("region", "us-east-1", "cloud region")
	instanceType := fs.String("instance-type", "g4dn.xlarge", "instance type")
	keyName := fs.String("key-name", "opendeploy", "SSH key name")
	publicKeyPath := fs.String("public-key", "", "path to SSH public key")
	infraDir := fs.String("infra-dir", "infra/aws", "path to terraform module")
	_ = fs.Parse(args)

	if *cloud != "aws" {
		fmt.Fprintln(os.Stderr, "only --cloud aws is supported in V1")
		os.Exit(1)
	}

	if *publicKeyPath == "" {
		fmt.Fprintln(os.Stderr, "missing --public-key path")
		os.Exit(1)
	}

	if _, err := exec.LookPath("terraform"); err != nil {
		fmt.Fprintln(os.Stderr, "terraform not found in PATH")
		os.Exit(1)
	}

	if err := terraformCmd(*infraDir, []string{"init"}); err != nil {
		fmt.Fprintf(os.Stderr, "terraform init failed: %v\n", err)
		os.Exit(1)
	}

	applyArgs := []string{
		"apply",
		"-auto-approve",
		"-var", fmt.Sprintf("region=%s", *region),
		"-var", fmt.Sprintf("instance_type=%s", *instanceType),
		"-var", fmt.Sprintf("key_name=%s", *keyName),
		"-var", fmt.Sprintf("public_key_path=%s", *publicKeyPath),
	}
	if err := terraformCmd(*infraDir, applyArgs); err != nil {
		fmt.Fprintf(os.Stderr, "terraform apply failed: %v\n", err)
		os.Exit(1)
	}

	publicIP, err := terraformOutput(*infraDir, "public_ip")
	if err != nil {
		fmt.Fprintf(os.Stderr, "terraform output failed: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("✅ Cloud instance provisioned")
	fmt.Printf("Public IP: %s\n", publicIP)
	fmt.Printf("Next: ./deploy.sh ec2-user@%s\n", publicIP)
}

func terraformCmd(dir string, args []string) error {
	cmdArgs := append([]string{"-chdir=" + dir}, args...)
	c := exec.Command("terraform", cmdArgs...)
	c.Stdout = os.Stdout
	c.Stderr = os.Stderr
	c.Stdin = os.Stdin
	return c.Run()
}

func terraformOutput(dir, name string) (string, error) {
	c := exec.Command("terraform", "-chdir="+dir, "output", "-raw", name)
	output, err := c.Output()
	if err != nil {
		return "", err
	}
	return string(output), nil
}

func printUsage() {
	fmt.Println("OpenDeploy CLI")
	fmt.Println("Usage:")
	fmt.Println("  opendeploy run <model> [--api-key <key>] [--strategy cheapest --region <region> --instance-type <type> --max-price <usd>]")
	fmt.Println("  opendeploy schedule --region <region> --instance-type <type> [--max-price <usd>] [--on-demand-price <usd>] [--lookback-minutes <n>]")
	fmt.Println("  opendeploy deploy --cloud aws --public-key <path> [--region <region>] [--instance-type <type>] [--key-name <name>]")
	fmt.Println("")
	fmt.Println("Example:")
	fmt.Println("  opendeploy run tiny-llama-chat")
	fmt.Println("  opendeploy run tiny-llama-chat --strategy cheapest --region us-east-1 --instance-type g5.xlarge --max-price 1.00")
	fmt.Println("  opendeploy schedule --region us-east-1 --instance-type g5.xlarge --max-price 1.00 --on-demand-price 1.20")
	fmt.Println("  opendeploy deploy --cloud aws --public-key ~/.ssh/id_rsa.pub")
}
