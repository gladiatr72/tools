
# mkeksauth

The EKS servicer utilizes a Kubernetes controller that is responsible
for mapping IAM users and roles to _keys_ (aka: Kube _users_) that can
be used to construct Kubernetes RBAC [Cluster]Roles.  The cluster-side
half of this mechanism operates from a _Daemonset_ named _aws-node_.

The configmap for _aws-node_:


```yaml

     1  apiVersion: v1
     2  kind: ConfigMap
     3  metadata:
     4    name: aws-auth
     5    namespace: kube-system
     6  data:
     7    mapRoles: |
     8      - rolearn: arn:aws:iam::442900888080:role/dev-1-avocado-node
     9        username: system:node:{{EC2PrivateDNSName}}
    10        groups:
    11        - system:masters
    12      - rolearn: arn:aws:iam::442900888080:role/stephen@revsys
    13        username: stephen@revsys
    14        groups:
    15        - system:masters
    16    mapUsers: |
    17      - userarn: arn:aws:iam::442900888080:user/dmortenson
    18        username: dmortenson
    19        groups:
    20        - system:masters
    21      - userarn: arn:aws:iam::442900888080:user/stephen.spencer
    22        username: stephen.spencer
    23        groups:
    24        - system:masters
    25      - userarn: arn:aws:iam::442900888080:user/fwiles
    26        username: fwiles
    27        groups:
    28        - system:masters

```

----

**Note**: the pipe (`|`) at the end of lines 7 and 29 signify the following value
to be a multi-line string, so, in essence, _aws-node_ configures itself with two
strings!

----

This utility is multi-purpose:

  1. make manual management of these maps more tolerable
  1. first step towards automating IAM group membership
  1. manage the kube node authorization entries for all ec2 instance profile roles


## Installation

**requires at least Python 3.6**

```sh

$ pwd
.../tf/v3/tools

$ python3 -m venv /your/path/to/.venv && . /your/path/to/.venv/bin/activate

$ pip install mkeksauth

```

## Usage

### results to stdout


$ mkeksauth --cluster-name dev-01 --group SomeAdminGroup system:masters

```


