package main

import (
	"fmt"
	"os"
	"os/exec"

	"github.com/spf13/cobra"
)

func newDeployCmd() *cobra.Command {
	var (
		cloud         string
		region        string
		instanceType  string
		keyName       string
		publicKeyPath string
		infraDir      string
	)

	cmd := &cobra.Command{
		Use:   "deploy",
		Short: "Provision a cloud GPU instance via Terraform",
		Long: `Uses Terraform to spin up a GPU-capable cloud instance with
Docker pre-installed, ready to receive the OpenDeploy stack.`,
		Example: `  opendeploy deploy --cloud aws --public-key ~/.ssh/id_rsa.pub
  opendeploy deploy --cloud aws --region us-west-2 --instance-type g5.2xlarge --public-key ~/.ssh/id_rsa.pub`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if cloud != "aws" {
				return fmt.Errorf("only --cloud aws is supported in V1")
			}
			if publicKeyPath == "" {
				return fmt.Errorf("--public-key is required")
			}
			if _, err := exec.LookPath("terraform"); err != nil {
				return fmt.Errorf("terraform not found in PATH")
			}

			if err := terraformCmd(infraDir, []string{"init"}); err != nil {
				return fmt.Errorf("terraform init failed: %w", err)
			}

			applyArgs := []string{
				"apply", "-auto-approve",
				"-var", fmt.Sprintf("region=%s", region),
				"-var", fmt.Sprintf("instance_type=%s", instanceType),
				"-var", fmt.Sprintf("key_name=%s", keyName),
				"-var", fmt.Sprintf("public_key_path=%s", publicKeyPath),
			}
			if err := terraformCmd(infraDir, applyArgs); err != nil {
				return fmt.Errorf("terraform apply failed: %w", err)
			}

			publicIP, err := terraformOutput(infraDir, "public_ip")
			if err != nil {
				return fmt.Errorf("terraform output failed: %w", err)
			}

			fmt.Println("✅ Cloud instance provisioned")
			fmt.Printf("Public IP: %s\n", publicIP)
			fmt.Printf("Next: ./deploy.sh ec2-user@%s\n", publicIP)
			return nil
		},
	}

	cmd.Flags().StringVar(&cloud, "cloud", "aws", "Cloud provider (aws)")
	cmd.Flags().StringVar(&region, "region", "us-east-1", "Cloud region")
	cmd.Flags().StringVar(&instanceType, "instance-type", "g4dn.xlarge", "Instance type")
	cmd.Flags().StringVar(&keyName, "key-name", "opendeploy", "SSH key name")
	cmd.Flags().StringVar(&publicKeyPath, "public-key", "", "Path to SSH public key")
	cmd.Flags().StringVar(&infraDir, "infra-dir", "infra/aws", "Path to Terraform module")

	_ = cmd.MarkFlagRequired("public-key")

	return cmd
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
