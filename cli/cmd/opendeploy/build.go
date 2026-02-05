package main

import (
	"fmt"
	"os/exec"

	"github.com/spf13/cobra"
)

func newBuildCmd() *cobra.Command {
	var (
		target   string
		model    string
		format   string
		quant    string
		version  string
		output   string
		registry string
		push     bool
	)

	cmd := &cobra.Command{
		Use:   "build",
		Short: "Build a model artifact for edge deployment",
		Long: `Quantizes a model to GGUF or ONNX format and pushes the
artifact to a local or OCI-compatible registry for edge deployment.`,
		Example: `  opendeploy build --target edge --model TinyLlama/TinyLlama-1.1B-Chat-v1.0
  opendeploy build --target edge --model my-model --format onnx --quant int8`,
		RunE: func(cmd *cobra.Command, args []string) error {
			if target != "edge" {
				return fmt.Errorf("only --target edge is supported")
			}
			if model == "" {
				return fmt.Errorf("--model is required")
			}

			python := "python"
			if _, err := exec.LookPath(python); err != nil {
				return fmt.Errorf("python not found in PATH")
			}

			cmdArgs := []string{
				"scripts/edge/build.py",
				"--model", model,
				"--format", format,
				"--quant", quant,
				"--output", output,
				"--registry", registry,
				"--push", fmt.Sprintf("%v", push),
			}
			if version != "" {
				cmdArgs = append(cmdArgs, "--version", version)
			}

			c := exec.Command(python, cmdArgs...)
			c.Stdout = cmd.OutOrStdout()
			c.Stderr = cmd.ErrOrStderr()
			if err := c.Run(); err != nil {
				return fmt.Errorf("edge build failed: %w", err)
			}
			return nil
		},
	}

	cmd.Flags().StringVar(&target, "target", "edge", "Build target (edge)")
	cmd.Flags().StringVar(&model, "model", "", "Model name or path")
	cmd.Flags().StringVar(&format, "format", "auto", "Output format: auto | gguf | onnx")
	cmd.Flags().StringVar(&quant, "quant", "q4_0", "Quantization preset: q4_0 | q4_k_m | int8")
	cmd.Flags().StringVar(&version, "version", "", "Artifact version tag (default: timestamp)")
	cmd.Flags().StringVar(&output, "output", "artifacts/edge", "Output directory")
	cmd.Flags().StringVar(&registry, "registry", "artifacts/registry", "Registry path or oci:// URL")
	cmd.Flags().BoolVar(&push, "push", true, "Push artifact to registry")

	_ = cmd.MarkFlagRequired("model")

	return cmd
}
