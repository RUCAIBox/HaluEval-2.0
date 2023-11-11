# coding: utf-8
import os
import json
import time
import openai
import requests
import multiprocessing
from tqdm import tqdm
from main import check_exist


def get_access_token():
    url = "https://hi-open.zhipin.com/open-apis/auth/tenant_access_token/internal"
    payload = json.dumps(
        {
            "app_id": "bli_yt3xllynei5rqqdj",
            "app_secret": "dd9684e41df14f69a4244583ca03ac54",
        }
    )
    headers = {"Content-Type": "application/json"}
    response = requests.request("POST", url, headers=headers, data=payload)
    data = json.loads(response.text)
    return data["data"]["tenant_access_token"]


def chatgpt_hi_request(
    message,
    # sys_msg="You are good at Text-to-SQL",
    model="4",
    # temperature=1.0,
    # top_p=0.9,
):
    """
    model type
    2: GPT3.5
    4: GPT4-8k
    5: GPT-4-32k
    """
    url = "https://hi-open.zhipin.com/open-apis/ai/open/api/send/message"
    headers = {
        "Authorization": "Bearer {0}".format(get_access_token()),
        "Content-Type": "application/json",
    }
    messages = [
        # {"role": "system", "content": sys_msg},
        {"role": "user", "content": message},
    ]
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            # "temperature": temperature,
            # "top_p": top_p,
        }
    )
    response = requests.request("POST", url, headers=headers, data=payload)
    data = json.loads(response.text)
    # if data['code'] != 0:
    #     print(data)
    return data["data"]["choices"][0]["message"]["content"]


def complete(query):
    input = query["input"]
    count = 0
    while True:
        if count > 20:
            res = "NO"
            break
        try:
            res = chatgpt_hi_request(input)
            break
        except Exception as e:
            print("Exception: %s\nRetrying..." % e)
            count += 1
    query["llm_output"] = res
    return query


if __name__ == "__main__":
    data_dir = "./rlhf_data/"
    save_dir = "./rlhf/"
    hallu_prompt = """You are presented with an answer in response to a query. Your task is to list all hallucinations in the answer. If no hallucinations are found, your response should be "NO".\nContext: <query>: {query} <answer>: {answer}\nResponse: """
    correct_prompt = """You are given a piece of answer text to a query. Based on the hallucination information present in the answer, your task is to revise and correct the answer text.\nContext: <query>: {query} <answer>: {answer}\nHallucination in the answer:\n{hallucination}\nResponse: According to the above information, the original answer can be revised as:\n"""
    check_exist(save_dir)
    files = [
        "Bio-Medical",
        "Finance",
        "Science",
        "Education",
        "Open-Domain",
    ]
    num_process = 145
    chunk_size = 1
    for file in files:
        save_data = []
        data_path = os.path.join(data_dir, file + ".json")
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        prompts = [
            hallu_prompt.format(query=data[i]["user_query"], answer=data[i]["response"])
            for i in range(len(data))
        ]
        for i in range(len(data)):
            data[i]["input"] = prompts[i]
        res_lst = []
        with multiprocessing.Pool(num_process) as p:
            results = p.imap_unordered(complete, data, chunksize=chunk_size)
            for res in tqdm(results, total=len(data)):
                res_lst.append(
                    {
                        "id": res["id"],
                        "user_query": res["user_query"],
                        "original_response": res["response"],
                        "corrected_response": res["response"],
                        "hallucination": res["llm_output"],
                    }
                )
            res_lst = sorted(res_lst, key=lambda x: x["id"])
        filtered_res_lst = [i for i in res_lst if "NO" not in i["hallucination"]]
        count = 0
        while count < 5:
            prompts = [
                correct_prompt.format(
                    query=filtered_res_lst[i]["user_query"],
                    answer=filtered_res_lst[i]["corrected_response"],
                    hallucination=filtered_res_lst[i]["hallucination"],
                )
                for i in range(len(filtered_res_lst))
            ]
            for i in range(len(filtered_res_lst)):
                filtered_res_lst[i]["input"] = prompts[i]
            res_lst = []
            with multiprocessing.Pool(num_process) as p:
                results = p.imap_unordered(
                    complete, filtered_res_lst, chunksize=chunk_size
                )
                for res in tqdm(results, total=len(filtered_res_lst)):
                    res_lst.append(
                        {
                            "id": res["id"],
                            "user_query": res["user_query"],
                            "original_response": res["original_response"],
                            "corrected_response": res["llm_output"],
                        }
                    )
                res_lst = sorted(res_lst, key=lambda x: x["id"])
            prompts = [
                hallu_prompt.format(
                    query=res_lst[i]["user_query"],
                    answer=res_lst[i]["corrected_response"],
                )
                for i in range(len(res_lst))
            ]
            for i in range(len(res_lst)):
                res_lst[i]["input"] = prompts[i]
            check_lst = []
            with multiprocessing.Pool(num_process) as p:
                results = p.imap_unordered(complete, res_lst, chunksize=chunk_size)
                for res in tqdm(results, total=len(res_lst)):
                    check_lst.append(
                        {
                            "id": res["id"],
                            "user_query": res["user_query"],
                            "original_response": res["original_response"],
                            "corrected_response": res["corrected_response"],
                            "hallucination": res["llm_output"],
                        }
                    )
                check_lst = sorted(check_lst, key=lambda x: x["id"])
            save_lst = [
                {
                    "id": i["id"],
                    "user_query": i["user_query"],
                    "original_response": i["original_response"],
                    "corrected_response": i["corrected_response"],
                }
                for i in check_lst
                if "NO" in i["hallucination"]
            ]
            save_data.extend(save_lst)
            filtered_res_lst = [i for i in check_lst if "NO" not in i["hallucination"]]
            filtered_res_lst = [
                {
                    "id": i["id"],
                    "user_query": i["user_query"],
                    "original_response": i["original_response"],
                    "corrected_response": i["corrected_response"],
                    "hallucination": i["hallucination"],
                }
                for i in check_lst
            ]
            count += 1
        save_lst = [
            {
                "id": i["id"],
                "user_query": i["user_query"],
                "original_response": i["original_response"],
                "corrected_response": i["corrected_response"],
            }
            for i in filtered_res_lst
        ]
        save_data.extend(save_lst)
        save_path = os.path.join(save_dir, file + ".json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
