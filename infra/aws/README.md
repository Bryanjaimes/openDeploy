# OpenDeploy V1 (AWS)

## Prereqs
- Terraform installed
- AWS credentials configured (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
- An SSH key pair (public key file)

## Deploy

```bash
terraform -chdir=infra/aws init
terraform -chdir=infra/aws apply \
  -var "key_name=opendeploy" \
  -var "public_key_path=~/.ssh/id_rsa.pub"
```

Outputs:
- `public_ip`
- `ssh_user`

## Next: Deploy the app

```bash
./deploy.sh ec2-user@<public_ip>
```
