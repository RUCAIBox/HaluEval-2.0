#!/bin/bash

export OPENAI_API_KEY="sk-uQgp6DoH8VpwMphgC44e7f04DdA24f37B5A6C2B899A9F040"
export OPENAI_API_BASE="https://api.chatgpt-3.vip/v1"
echo "OPENAI_API_KEY is set to: $OPENAI_API_KEY"
echo "OPENAI_API_BASE is set to: $OPENAI_API_BASE"

# DirList=("flan" "sharegpt" "sinstruct" "sinstruct_sharegpt" "sinstruct_sharegpt_flan_10k")
DirList=("sharegpt" "sinstruct" "sinstruct_sharegpt" "sinstruct_sharegpt_flan_10k")

for dir in ${DirList[*]}; do
    nohup python -u fact.py --all-files --model llama-7b --data-dir "./sft2/$dir" --save-dir "./fact/$dir" >> ./log/sft_fact_$dir.log 2>&1 &
done
