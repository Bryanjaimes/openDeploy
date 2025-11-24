#!/bin/bash

# OpenDeploy AWS Provisioner
# Provisions a t3.medium instance with Docker installed, ready for deployment.

INSTANCE_TYPE="t3.medium"
REGION="us-east-1"
KEY_NAME="opendeploy-key"
SG_NAME="opendeploy-sg"
AMI_ID="ami-051f7e7f6c2f40dc1" # Amazon Linux 2023 (US-East-1) - Update if region changes

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting OpenDeploy AWS Provisioner...${NC}"

# 1. Check for AWS CLI
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed. Please install it and run 'aws configure'."
    exit 1
fi

# 2. Create Key Pair (if not exists)
if [ ! -f "${KEY_NAME}.pem" ]; then
    echo "Creating SSH Key Pair: ${KEY_NAME}..."
    aws ec2 create-key-pair --key-name $KEY_NAME --query 'KeyMaterial' --output text > ${KEY_NAME}.pem
    chmod 400 ${KEY_NAME}.pem
else
    echo "Key Pair ${KEY_NAME}.pem already exists. Skipping."
fi

# 3. Create Security Group
echo "Setting up Security Group..."
SG_ID=$(aws ec2 create-security-group --group-name $SG_NAME --description "OpenDeploy Security Group" --output text 2>/dev/null)
if [ -z "$SG_ID" ]; then
    # If fails, it might already exist, try to fetch it
    SG_ID=$(aws ec2 describe-security-groups --group-names $SG_NAME --query 'SecurityGroups[0].GroupId' --output text)
    echo "Using existing Security Group: $SG_ID"
else
    # Add Rules
    aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22 --cidr 0.0.0.0/0
    aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 8000 --cidr 0.0.0.0/0 # Backend
    aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 3000 --cidr 0.0.0.0/0 # Frontend
fi

# 4. Launch Instance
echo "Launching EC2 Instance ($INSTANCE_TYPE)..."

# User Data script to install Docker
USER_DATA='#!/bin/bash
yum update -y
yum install -y docker git
service docker start
usermod -a -G docker ec2-user
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
'

INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_ID \
    --count 1 \
    --instance-type $INSTANCE_TYPE \
    --key-name $KEY_NAME \
    --security-group-ids $SG_ID \
    --user-data "$USER_DATA" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "Instance launched: $INSTANCE_ID"
echo "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids $INSTANCE_ID

# 5. Get Public IP
PUBLIC_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo -e "${GREEN}✅ Provisioning Complete!${NC}"
echo "Instance IP: $PUBLIC_IP"
echo "SSH Key: ${KEY_NAME}.pem"
echo ""
echo "To deploy your code, run:"
echo "./deploy.sh ec2-user@$PUBLIC_IP"
