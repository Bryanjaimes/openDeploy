package main

import (
	"testing"
	"time"
)

func TestSelectCheapest(t *testing.T) {
	now := time.Now()

	tests := []struct {
		name     string
		prices   []SpotPrice
		maxPrice float64
		wantAZ   string
		wantErr  bool
	}{
		{
			name:     "empty prices",
			prices:   nil,
			maxPrice: 0,
			wantAZ:   "",
			wantErr:  true,
		},
		{
			name: "single price, no limit",
			prices: []SpotPrice{
				{Provider: "AWS", AvailabilityZone: "us-east-1a", InstanceType: "g5.xlarge", PriceUSD: 0.50, Timestamp: now},
			},
			maxPrice: 0,
			wantAZ:   "us-east-1a",
			wantErr:  false,
		},
		{
			name: "picks cheapest of three",
			prices: []SpotPrice{
				{Provider: "AWS", AvailabilityZone: "us-east-1a", InstanceType: "g5.xlarge", PriceUSD: 0.80, Timestamp: now},
				{Provider: "AWS", AvailabilityZone: "us-east-1b", InstanceType: "g5.xlarge", PriceUSD: 0.30, Timestamp: now},
				{Provider: "AWS", AvailabilityZone: "us-east-1c", InstanceType: "g5.xlarge", PriceUSD: 0.55, Timestamp: now},
			},
			maxPrice: 0,
			wantAZ:   "us-east-1b",
			wantErr:  false,
		},
		{
			name: "respects max price",
			prices: []SpotPrice{
				{Provider: "AWS", AvailabilityZone: "us-east-1a", InstanceType: "g5.xlarge", PriceUSD: 0.80, Timestamp: now},
				{Provider: "AWS", AvailabilityZone: "us-east-1b", InstanceType: "g5.xlarge", PriceUSD: 0.30, Timestamp: now},
			},
			maxPrice: 0.50,
			wantAZ:   "us-east-1b",
			wantErr:  false,
		},
		{
			name: "all exceed max price",
			prices: []SpotPrice{
				{Provider: "AWS", AvailabilityZone: "us-east-1a", InstanceType: "g5.xlarge", PriceUSD: 2.00, Timestamp: now},
				{Provider: "AWS", AvailabilityZone: "us-east-1b", InstanceType: "g5.xlarge", PriceUSD: 1.50, Timestamp: now},
			},
			maxPrice: 1.00,
			wantAZ:   "",
			wantErr:  true,
		},
		{
			name: "exact max price match",
			prices: []SpotPrice{
				{Provider: "AWS", AvailabilityZone: "us-east-1a", InstanceType: "g5.xlarge", PriceUSD: 1.00, Timestamp: now},
			},
			maxPrice: 1.00,
			wantAZ:   "us-east-1a",
			wantErr:  false,
		},
		{
			name: "multi-cloud picks cheapest provider",
			prices: []SpotPrice{
				{Provider: "AWS", AvailabilityZone: "us-east-1a", InstanceType: "g5.xlarge", PriceUSD: 0.80, Timestamp: now},
				{Provider: "GCP", AvailabilityZone: "us-central1-a", InstanceType: "a2-highgpu-1g", PriceUSD: 0.45, Timestamp: now},
			},
			maxPrice: 0,
			wantAZ:   "us-central1-a",
			wantErr:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := selectCheapest(tt.prices, tt.maxPrice)
			if (err != nil) != tt.wantErr {
				t.Errorf("selectCheapest() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if !tt.wantErr && got.AvailabilityZone != tt.wantAZ {
				t.Errorf("selectCheapest() AZ = %q, want %q", got.AvailabilityZone, tt.wantAZ)
			}
		})
	}
}

func TestSelectCheapest_PrefersCheapestWhenMultipleBelowMax(t *testing.T) {
	now := time.Now()
	prices := []SpotPrice{
		{Provider: "AWS", AvailabilityZone: "us-east-1a", InstanceType: "g5.xlarge", PriceUSD: 0.40, Timestamp: now},
		{Provider: "AWS", AvailabilityZone: "us-east-1b", InstanceType: "g5.xlarge", PriceUSD: 0.35, Timestamp: now},
		{Provider: "AWS", AvailabilityZone: "us-east-1c", InstanceType: "g5.xlarge", PriceUSD: 0.60, Timestamp: now},
	}

	got, err := selectCheapest(prices, 0.50)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// selectCheapest sorts internally, so cheapest (0.35) wins
	if got.AvailabilityZone != "us-east-1b" {
		t.Errorf("expected us-east-1b, got %s", got.AvailabilityZone)
	}
}

func TestResolveAwsCli_Override(t *testing.T) {
	t.Setenv("AWS_CLI_PATH", "/custom/aws")
	path, err := resolveAwsCli()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if path != "/custom/aws" {
		t.Errorf("expected /custom/aws, got %s", path)
	}
}

func TestResolveGcloudCli_Override(t *testing.T) {
	t.Setenv("GCLOUD_CLI_PATH", "/custom/gcloud")
	path, err := resolveGcloudCli()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if path != "/custom/gcloud" {
		t.Errorf("expected /custom/gcloud, got %s", path)
	}
}
