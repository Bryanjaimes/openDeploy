package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

// rootCmd is the base command for the OpenDeploy CLI.
var rootCmd = &cobra.Command{
	Use:   "opendeploy",
	Short: "OpenDeploy – Sovereign AI Cloud Platform",
	Long: `OpenDeploy is an open-source, multi-cloud orchestration engine
that treats AI models as first-class citizens. Deploy, optimize,
and serve models across any compute substrate with a single command.`,
}

func init() {
	rootCmd.AddCommand(newRunCmd())
	rootCmd.AddCommand(newBuildCmd())
	rootCmd.AddCommand(newScheduleCmd())
	rootCmd.AddCommand(newDeployCmd())
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
