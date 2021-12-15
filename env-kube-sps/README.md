

# env-kube-sps

## goals

  * delivery of configuration elements by way of environment variables in a
  Kubernetes environment
  * provide curated access to configuration data for AWS services (e.g.: lambda)
  * sync configuration data to AWS System Manager's _Secure Parameter Store_
  subservice.
  * sync configuration data to a specified kubernetes namespace within an AWS
  EKS cluster


## summary


---
_env-kube-sps_ requires Python 3.  Particular attention was made to avoid
Python 3.6+-specific constructs (`str().format()` vs. _f-strings_)

---

This utility uses [Click](https://click.palletsprojects.com/en/7.x/).  Due
to its design, _help_ is displayed for whatever command is specified or
for the base/global command if one is not specified.  Placing flags for
one command in the conshellt of a different command will generate an error.


```sh

$ env-kube-sps --environment development --component staging --help

Usage: env-kube-sps [OPTIONS] COMMAND [ARGS]...

Options:
  --environment TEXT  [required]
  --component TEXT    [required]
  -v, --verbose
  --help              Show this message and exit.

Commands:
  list-sps
  purge-sps
  sync-to-eks
  sync-to-sps


```

### commands and associated flags

  * global:
    * `--environment` ✰  (`BOVISYNC_ENVIRONMENT`)
    * `--component`  ✰  (`BOVISYNC_COMPONENT`)
    * `--verbose` or `-v` ♬
  * sync-to-sps
    * `--input-file`
    * `--set-key` or `-k` ♬
    * `--with-label`
    * `--secret`
  * sync-to-eks
    * `--cluster-name`
    * `--namespace`
    * `--with-label`
  * list-sps
    * `--regex`
  * purge-sps
    * `--regex`


    ✰ - required argument -- can be set by the designated environment variable

    ♬ - supports multiple occurances



## installation


```sh

$ pip install terraform/kube/tools/env-kube-sps

```

---

**NOTE**: if using python 3.5, be sure to upgrade _pip_ before installing

---



## create parameters (`sync-to-sps`)


### notes

  * Parameter paths are set to `/deployment environment/component/key-name`
  * .. are encrypted using the KMS key: `/alias/[environment]/ssm`
    * _type_ can only be set at creation
  * .. are created as _standard_ parameters unless the value exceeds the 4k
  limit
    * _tier_ can only be set at creation


### ingestion (`sync-to-sps`)

There are currently two ways to input data:

 > using an _env_ formatted text file


given the source file:
```txt
A=B
cats_and_dogs=livingtogether
TATERS=GRAVY
```

```shell

$ export BOVISYNC_ENVIRONMENT=global BOVISYNC_COMPONENT=squeegee

$ env-kube-sps -v sync-to-sps --input-file /path/to/file.env

KMS Key, alias/global/ssm, found in us-east-1
3 variables ingested
/global/squeegee/A not found. Creating...
/global/squeegee/cats_and_dogs not found. Creating...
/global/squeegee/TATERS not found. Creating...

```

  > using `--set-key` (or `-k`)


```shell

$ export BOVISYNC_ENVIRONMENT=global BOVISYNC_COMPONENT=squeegee

$ env-kube-sps -v sync-to-sps --set-key KEY1=VALUE1 --set-key KEY2=VALUE2
KMS Key, alias/global/ssm, found in us-east-1
2 variables ingested
/global/lambda/KEY1 not found. Creating...
/global/lambda/KEY2 not found. Creating...

```

## update parameters (`sync-to-sps`)

To update parameters, add the `--update` flag to the _sync-to-sps_ command.

---

**NOTE**: Each parameter has a _version_ counter that is incremented on each
successful `put_parameter()` call regardless of whether or not the poasted
value is changed.  To avoid perforating parameter histories, the submitted
value is checked against the stored value before issuing a `put_parameter()`
call.

---


 > without `--update` with a different KEY1 value
```shell

$ export BOVISYNC_ENVIRONMENT=global BOVISYNC_COMPONENT=squeegee

$ env-kube-sps -v sync-to-sps --set-key KEY1=VALUE1B --set-key KEY2=VALUE2
KMS Key, alias/global/ssm, found in us-east-1
2 variables ingested
/global/lambda/KEY1 found
/global/lambda/KEY1: exists and --update=False
/global/lambda/KEY2 found
/global/lambda/KEY2: exists and --update=False

```

 > with `--update` with a different KEY1 value
```shell

$ export BOVISYNC_ENVIRONMENT=global BOVISYNC_COMPONENT=squeegee

$ env-kube-sps -v sync-to-sps --set-key KEY1=VALUE1B --set-key KEY2=VALUE2
KMS Key, alias/global/ssm, found in us-east-1
2 variables ingested
/global/squeegee/KEY1 found
Updating /global/squeegee/KEY1...
/global/squeegee/KEY2 found
/global/squeegee/KEY2: unchanged.  Skipping...

```


### list parameters (`list-sps`)


```shell

$ export BOVISYNC_ENVIRONMENT=global BOVISYNC_COMPONENT=squeegee

$ env-kube-sps -v list-sps
A
KEY1
KEY2
TATERS
cats_and_dogs


$ env-kube-sps -v list-sps --regex KEY.
KEY1
KEY2

$ env-kube-sps -v list-sps --regex [^_]+_and_.*
cats_and_dogs

```


### delete parameters (`purge-sps`)

---

**NOTE**: deleting a parameter does not preserve the parameter's history.
Once deleted, it must be created as if it never was.

---


```shell

$ export BOVISYNC_ENVIRONMENT=global BOVISYNC_COMPONENT=squeegee


env-kube-sps -v purge-sps --regex '[^_]+_and_.*'
Confirm [y/N]: y
/global/squeegee/cats_and_dogs deleted


:# env-kube-sps -v purge-sps --regex 'KEY\d'
Confirm [y/N]: y
/global/squeegee/KEY1 deleted
/global/squeegee/KEY2 deleted


$ env-kube-sps -v list-sps
A
TATERS


$ env-kube-sps -v purge-sps --regex '.*'
/global/squeegee/A deleted
/global/squeegee/TATERS deleted


```


## sync secrets to EKS cluster


```shell
env-kube-sps --environment staging --component api -v sync-to-eks --cluster-name development-01 --namespace [kube-namespace]
```

After the environment is synced, it will be used by all new pods. To force new pods: `kubectl delete pod -n [kube-namespace] -l app=api`


## New Environment Setup

By default, env-kube-sps uses the _SecureString_ type for at-rest encryption
of parameters.  The KMS key to use is based on `/alias/[environment]/ssm` as
its naming pattern.  If a KMS alias does not exist (pointing to a valid key)
that follows this pattern, an error will be thrown and the utility will exit.

To initialize a new _environment✰_ requires a new kms key.


  ✰ pertaining to the second element in a parameter's path


  > creating a workspace for a new _demo_ environment

```shell

$ cd ${GITROOT}/terraform/kube/kms

$ terraform workspace new demo

$ terraform apply

(etc)

```

The output from this terraform run includes the name of the IAM Policy that
can be attached to an IAM Role for access to an environment's parameters.

