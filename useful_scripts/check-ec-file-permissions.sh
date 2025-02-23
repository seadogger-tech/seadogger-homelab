#!/bin/bash

# List of directories to check
directories=(
  "/var/log/ceph"
  "/var/lib/ceph"
  "/rook-ceph/log"
  "/rook-ceph/data"
)

# Function to check directory permissions
check_permissions() {
  local dir=$1

  # Check if directory exists
  if [ -d "$dir" ]; then
    echo "Directory $dir exists."

    # Check if directory has read/write/execute permissions
    if [ -r "$dir" ] && [ -w "$dir" ] && [ -x "$dir" ]; then
      echo "Permissions: OK (read, write, execute)"
    else
      echo "Permissions: Missing read, write, or execute access"
    fi

    # Check owner and group
    owner=$(stat -c %U "$dir")
    group=$(stat -c %G "$dir")
    echo "Owner: $owner, Group: $group"

  else
    echo "Directory $dir does NOT exist!"
  fi
}

# Function to check on multiple nodes
check_on_node() {
  local node=$1
  echo "Checking directories on node: $node"
  
  for dir in "${directories[@]}"; do
    echo "-------------------------------------------------"
    echo "Checking directory: $dir"
    ssh "$node" "bash -s" < <(declare -f check_permissions; check_permissions "$dir")
    echo "-------------------------------------------------"
  done
}

# List of nodes to check
nodes=(
  "obiwan.local"
  "anakin.local"
  "rey.local"
)

# Loop through each node and perform checks
for node in "${nodes[@]}"; do
  check_on_node "$node"
done
