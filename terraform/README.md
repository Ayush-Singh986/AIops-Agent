# Cost-conscious AWS deployment

This Terraform configuration runs the existing Docker Compose demo on one Ubuntu EC2 instance. It is intended for learning, evaluation, and short-lived demonstrations—not for production workloads.

## What it creates

- One VPC and public subnet, with no NAT Gateway (which would add ongoing hourly and data-processing charges).
- One EC2 instance. The default is `t3a.small` with 2 vCPUs and 2 GiB RAM; change to `t3a.medium` if the five-container stack runs short of memory.
- One encrypted 20 GiB gp3 root disk, deleted with the instance.
- An instance role with `AmazonSSMManagedInstanceCore` for AWS Systems Manager access and a narrowly scoped `bedrock:InvokeModel` permission for the Nova Pro US inference profile.
- A security group with **no inbound rules**. SSH, the app, Grafana, Prometheus, and Locust are not exposed publicly.
- First-boot setup that installs Docker Compose, clones the configured public Git repository, and starts the stack.

The public IPv4 address is needed for outbound internet access without a NAT Gateway. It does not make the app reachable from the internet because the security group allows no inbound traffic.

## Prerequisites

1. An AWS account with permission to create VPC, EC2, IAM, and Systems Manager resources.
2. AWS CLI configured for the target account and region.
3. Terraform 1.5 or newer.
4. AWS Session Manager plugin installed on your workstation to open shell and port-forwarding sessions.

The EC2 instance needs outbound internet access to install operating-system packages, reach Systems Manager and Amazon Bedrock, and pull Docker images and the public repository. No AWS keys, GitHub tokens, or Bedrock credentials are placed in Terraform or user data. Terraform grants the instance role access only to invoke the configured Nova Pro US inference profile; see [`bedrock-policy.json`](bedrock-policy.json).

For an already-running EC2 instance created outside this Terraform configuration:

1. In AWS IAM, create a policy from [`bedrock-policy.json`](bedrock-policy.json).
2. Make sure the EC2 instance has an IAM role trusted by the EC2 service. Attach the new policy to that role. If the instance already has a role for Systems Manager, add the policy to that existing role rather than replacing it.
3. In the EC2 console, select the instance and choose **Actions → Security → Modify IAM role**, then attach the role. Role changes do not require putting credentials on the server.
4. On the instance, verify the role is visible and configured:

   ```bash
   python -c 'import boto3; print(boto3.client("sts", region_name="us-east-1").get_caller_identity()["Arn"])'
   ```

Do not add access keys to the project or shell startup files. Bedrock model availability/entitlement in the account and selected region is separate from IAM credentials and must also be enabled.

## Deploy

From this directory:

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

The default region is `us-east-1` (US East / N. Virginia). Override settings using command-line variables when needed, for example:

```bash
terraform apply -var="aws_region=us-west-2" -var="instance_type=t3a.medium"
```

Terraform uses local state by default. Keep `terraform.tfstate` private and backed up; it is ignored by Git. For a shared or production environment, configure a protected remote state backend with locking before applying.

## Connect without opening a port

The instance registers with Systems Manager after boot. This can take a few minutes. Use the `instance_id` output:

```bash
terraform output -raw ssm_shell_command
```

Run the printed command to open a shell. On the instance, check bootstrap and Compose status:

```bash
sudo cloud-init status --long
sudo tail -n 100 /var/log/aiops-bootstrap.log
cd /opt/aiops-agent
sudo docker compose ps
sudo docker compose logs --tail=100
```

To open Grafana locally without making it public, use the printed tunnel command:

```bash
terraform output -raw grafana_tunnel_command
```

Run that command in a terminal, then visit `http://127.0.0.1:3000`. Terraform generates a random Grafana password at first boot and stores it in the root-only `/opt/aiops-agent/.env` file on the instance, not in Terraform state. Retrieve it through the SSM shell with:

```bash
sudo sed -n 's/^GF_SECURITY_ADMIN_PASSWORD=//p' /opt/aiops-agent/.env
```

Keep the password private. For local Compose runs, run `bash scripts/setup-env.sh` from the project root before starting the stack. It creates a random password in a protected `.env` file if one is not already configured. Compose reads the file automatically and refuses to start Grafana if the password is absent. For Prometheus and Locust, create separate SSM port-forwarding sessions for remote ports `9090` and `8089`, respectively. The app can be forwarded on `8000`. Keep chaos endpoints restricted to your own local tunnel; they intentionally disrupt the demo and have no authentication.

The AWS identity on your workstation needs permissions to start, resume, and terminate Systems Manager sessions to this instance. Follow your organization's least-privilege policy.

## Cost and resource notes

- The instance and its public IPv4 address are the main ongoing charges; the VPC, subnet, route table, and security group have no hourly charge.
- `t3a.small` and 20 GiB gp3 are conservative demo defaults, not an AWS Free Tier guarantee. AWS pricing varies by region, account eligibility, usage, and tax. Check the AWS Pricing Calculator before applying.
- A small instance may run out of memory under load or while Locust is active. Stop Locust when idle or use `t3a.medium` if the host is memory constrained.
- Stopping the instance reduces compute charges but does not remove EBS or necessarily public IPv4 charges. Destroy the resources when finished to stop ongoing charges.
- No NAT Gateway, load balancer, managed database, or paid monitoring service is provisioned.

## Cleanup

Review the resources Terraform plans to remove, then run:

```bash
terraform destroy
```

This deletes the instance and its root disk, including local Prometheus/Grafana data and logs. Back up anything you need before destroying the stack.

## Important safety limits

- This is a demo deployment, not a production-ready, highly available, or hardened service.
- The project’s remediation defaults and chaos endpoints are designed for an isolated lab. Do not run the agent evaluator or fault experiments against production.
- Do not add public ingress rules for the app or Grafana without first adding authentication, TLS, and appropriate network restrictions.
- User data is logged on the instance at `/var/log/aiops-bootstrap.log`; it contains bootstrap commands and the public repository URL, not the generated Grafana password.
