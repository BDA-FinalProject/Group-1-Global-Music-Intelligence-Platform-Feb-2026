variable "project_name" {
  type = string
}

variable "env" {
  type = string
}

variable "github_repo" {
  description = "GitHub repo in org-or-user/repo-name form, e.g. octocat/retail-lake."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
