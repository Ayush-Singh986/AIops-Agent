output "instance_id" {
  description = "EC2 instance ID; use it as the target for AWS Systems Manager sessions."
  value       = aws_instance.demo.id
}

output "instance_public_ip" {
  description = "Public IP used only for outbound connectivity; the security group has no inbound rules."
  value       = aws_instance.demo.public_ip
}

output "aws_region" {
  description = "AWS region containing the instance."
  value       = var.aws_region
}

output "ssm_shell_command" {
  description = "Run this command with AWS CLI and the Session Manager plugin installed."
  value       = "aws ssm start-session --target ${aws_instance.demo.id} --region ${var.aws_region}"
}

output "grafana_tunnel_command" {
  description = "Forward local port 3000 to Grafana using AWS Systems Manager port forwarding."
  value       = "aws ssm start-session --target ${aws_instance.demo.id} --document-name AWS-StartPortForwardingSession --parameters '{\"portNumber\":[\"3000\"],\"localPortNumber\":[\"3000\"]}' --region ${var.aws_region}"
}
