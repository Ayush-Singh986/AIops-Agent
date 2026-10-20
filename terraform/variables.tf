variable "aws_region" {
  description = "AWS region in which to deploy the demo."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name applied to AWS resource tags."
  type        = string
  default     = "aiops-agent-demo"
}

variable "instance_type" {
  description = "EC2 instance size. t3a.small is the low-cost starting point; use t3a.medium if memory is constrained."
  type        = string
  default     = "t3a.small"
}

variable "root_volume_size_gb" {
  description = "Encrypted gp3 root disk size. Docker images and telemetry need persistent disk space."
  type        = number
  default     = 20

  validation {
    condition     = var.root_volume_size_gb >= 20 && var.root_volume_size_gb <= 100
    error_message = "root_volume_size_gb must be between 20 and 100 GB."
  }
}

variable "project_repo_url" {
  description = "Public Git URL the instance clones during first boot."
  type        = string
  default     = "https://github.com/Ayush-Singh986/AIops-Agent.git"
}

variable "project_repo_branch" {
  description = "Branch the instance checks out during first boot."
  type        = string
  default     = "main"
}
