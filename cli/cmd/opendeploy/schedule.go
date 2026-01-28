package main

import (
    "context"
    "encoding/json"
    "errors"
    "flag"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
    "sort"
    "strconv"
    "time"
)

type SpotPrice struct {
    AvailabilityZone string
    InstanceType     string
    PriceUSD         float64
    Timestamp        time.Time
}

func scheduleCmd(args []string) {
    fs := flag.NewFlagSet("schedule", flag.ExitOnError)
    region := fs.String("region", "us-east-1", "AWS region")
    instanceType := fs.String("instance-type", "g5.xlarge", "EC2 instance type")
    maxPrice := fs.Float64("max-price", 0, "max USD per hour for spot (0 = no limit)")
    onDemandPrice := fs.Float64("on-demand-price", 0, "optional on-demand USD per hour for savings estimate")
    lookbackMinutes := fs.Int("lookback-minutes", 60, "lookback window in minutes for spot price history")
    _ = fs.Parse(args)

    if err := printScheduleRecommendation(*region, *instanceType, *maxPrice, *onDemandPrice, time.Duration(*lookbackMinutes)*time.Minute); err != nil {
        fmt.Fprintf(os.Stderr, "scheduling failed: %v\n", err)
        os.Exit(1)
    }
}

func printScheduleRecommendation(region, instanceType string, maxPrice, onDemandPrice float64, lookback time.Duration) error {
    ctx := context.Background()
    prices, err := fetchSpotPrices(ctx, region, instanceType, lookback)
    if err != nil {
        return fmt.Errorf("spot price query failed: %w", err)
    }

    if len(prices) == 0 {
        return errors.New("no spot prices returned")
    }

    best, err := selectCheapest(prices, maxPrice)
    if err != nil {
        return err
    }

    fmt.Println("✅ AWS Spot schedule recommendation")
    fmt.Printf("Region: %s\n", region)
    fmt.Printf("Instance: %s\n", best.InstanceType)
    fmt.Printf("Availability Zone: %s\n", best.AvailabilityZone)
    fmt.Printf("Spot Price: $%.4f/hr (as of %s)\n", best.PriceUSD, best.Timestamp.Format(time.RFC3339))
    if onDemandPrice > 0 {
        savingsPct := (1 - (best.PriceUSD / onDemandPrice)) * 100
        fmt.Printf("Estimated savings vs on-demand: %.1f%%\n", savingsPct)
    }

    fmt.Println("Next: provision with this AZ and instance type when quota is approved.")
    return nil
}

type spotPriceHistoryResponse struct {
    SpotPriceHistory []struct {
        AvailabilityZone string    `json:"AvailabilityZone"`
        InstanceType     string    `json:"InstanceType"`
        SpotPrice        string    `json:"SpotPrice"`
        Timestamp        time.Time `json:"Timestamp"`
    } `json:"SpotPriceHistory"`
}

func fetchSpotPrices(ctx context.Context, region, instanceType string, lookback time.Duration) ([]SpotPrice, error) {
    if lookback <= 0 {
        lookback = 60 * time.Minute
    }

    startTime := time.Now().Add(-lookback).UTC().Format(time.RFC3339)
    endTime := time.Now().UTC().Format(time.RFC3339)

    awsCli, err := resolveAwsCli()
    if err != nil {
        return nil, err
    }

    cmd := exec.CommandContext(
        ctx,
        awsCli,
        "ec2",
        "describe-spot-price-history",
        "--instance-types", instanceType,
        "--product-descriptions", "Linux/UNIX",
        "--start-time", startTime,
        "--end-time", endTime,
        "--max-items", "1000",
        "--region", region,
        "--output", "json",
    )

    output, err := cmd.Output()
    if err != nil {
        if exitErr, ok := err.(*exec.ExitError); ok {
            return nil, fmt.Errorf("aws cli error: %s", string(exitErr.Stderr))
        }
        return nil, err
    }

    var resp spotPriceHistoryResponse
    if err := json.Unmarshal(output, &resp); err != nil {
        return nil, err
    }

    latestByAz := map[string]SpotPrice{}
    for _, entry := range resp.SpotPriceHistory {
        if entry.AvailabilityZone == "" || entry.SpotPrice == "" {
            continue
        }

        priceVal, err := strconv.ParseFloat(entry.SpotPrice, 64)
        if err != nil {
            continue
        }

        candidate := SpotPrice{
            AvailabilityZone: entry.AvailabilityZone,
            InstanceType:     entry.InstanceType,
            PriceUSD:         priceVal,
            Timestamp:        entry.Timestamp,
        }

        if existing, ok := latestByAz[entry.AvailabilityZone]; !ok || candidate.Timestamp.After(existing.Timestamp) {
            latestByAz[entry.AvailabilityZone] = candidate
        }
    }

    prices := make([]SpotPrice, 0, len(latestByAz))
    for _, price := range latestByAz {
        prices = append(prices, price)
    }

    sort.Slice(prices, func(i, j int) bool {
        return prices[i].PriceUSD < prices[j].PriceUSD
    })

    return prices, nil
}

func resolveAwsCli() (string, error) {
    if override := os.Getenv("AWS_CLI_PATH"); override != "" {
        return override, nil
    }

    if path, err := exec.LookPath("aws"); err == nil {
        return path, nil
    }

    defaultPath := filepath.Join("C:", "Program Files", "Amazon", "AWSCLIV2", "aws.exe")
    if _, err := os.Stat(defaultPath); err == nil {
        return defaultPath, nil
    }

    return "", errors.New("aws cli not found; set AWS_CLI_PATH or add aws.exe to PATH")
}

func selectCheapest(prices []SpotPrice, maxPrice float64) (SpotPrice, error) {
    if len(prices) == 0 {
        return SpotPrice{}, errors.New("no spot prices available")
    }

    if maxPrice <= 0 {
        return prices[0], nil
    }

    for _, price := range prices {
        if price.PriceUSD <= maxPrice {
            return price, nil
        }
    }

    return SpotPrice{}, fmt.Errorf("no spot price at or below $%.4f/hr", maxPrice)
}
