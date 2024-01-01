#!/bin/bash

ModelList=("llama-2-7b-chat-hf")
DirList=("0-shot" "base" "character_info" "domain_info" "few-shot" "in-context_demo" "mannual_desc" "refine_q" "retrieved_demo" "reverse_pos" "synthetic_demo" "synthetic_desc" "wrong_demo")
for model in ${ModelList[*]}; do
    for dir in ${DirList[*]}; do
        nohup python -u fact.py --all-files --model $model --data-dir "./prompt_response_pure/$model/$dir" --save-dir "./fact/$model/$dir/" > ./fact_log/fact_$dir\_$model.log 2>&1 &
    done
done
