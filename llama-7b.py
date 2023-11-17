# coding: utf-8
import os

os.environ["CUDA_VISIBLE_DEVICES"] = "2"
import torch
import requests
import openai
import argparse
from tqdm import tqdm
import json
import time
import func_timeout
from func_timeout import func_set_timeout
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
)


def check_exist(path):
    """
    Check if the path exists, if not, create it.
    """
    if not os.path.exists(path):
        os.makedirs(path)


class Bot(object):
    """
    Base class for chatbot.
    """

    def __init__(self, model):
        self.model = model  # chat model
        self.model2path = {
            "llama-2-7b-chat-hf": "/media/public/models/huggingface/meta-llama/Llama-2-7b-chat-hf/",
            "llama-2-13b-chat-hf": "/media/public/models/huggingface/meta-llama/Llama-2-13b-chat-hf/",
            "alpaca-7b": "/media/public/models/huggingface/alpaca-7b/",
            "vicuna-7b": "/media/public/models/huggingface/vicuna-7b/",
            "vicuna-13b": "/media/public/models/huggingface/vicuna-13b-v1.1/",
            "llama-7b": "/media/public/models/huggingface/llama-7b/",
            # "llama-2-7b-hf": "/media/public/models/huggingface/meta-llama/Llama-2-7b-hf/",
            # "llama-2-13b-hf": "/media/public/models/huggingface/meta-llama/Llama-2-13b-hf/",
            # "bloom-7b1": "/media/public/models/huggingface/bigscience/bloom-7b1/",
        }  # local model path
        self.tokenizer = None
        self.llm = None

    def load_model(self, load_in_4bit, load_in_8bit):
        """
        Load local models and tokenizers.
        """
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cuda":
            device_id = torch.cuda.current_device()
            print(f"device: cuda:{device_id}")
        else:
            print(f"device: {self.device}")
        if self.model.startswith("vicuna"):  # vicuna-7b, vicuna-13b
            legacy = False
        else:
            legacy = True
        if self.model not in [
            "chatgpt",
            "text-davinci-002",
            "text-davinci-003",
        ]:
            model_path = self.model2path[self.model]
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
                use_fast=True,
                legacy=legacy,
            )
            if load_in_4bit:
                assert self.model.startswith("llama-2")
                self.llm = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                    device_map="auto",
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
            elif load_in_8bit:
                assert self.model.startswith("llama-2")
                self.llm = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                    device_map="auto",
                    load_in_8bit=True,
                )
            else:
                self.llm = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                    device_map="cuda",
                    torch_dtype=torch.float16,
                )


class Chatbot(Bot):
    """
    Chatbot for response generation.
    """

    def __init__(self, data_path, save_path, model, file):
        super().__init__(model)
        self.file = file  # file name
        self.data_path = data_path  # path to data
        self.save_path = save_path  # path to save
        self.save_data = []  # data to save
        self.max_retry = 500  # max retry times
        self.frequency = 300  # save frequency

    def load_data(self, part=0):
        """
        Load data from data path.
        """
        with open(self.data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if part:
                data = data[:part]
            print(f"Loading data from {self.data_path}, total {len(data)}")
        return data

    def save(self):
        """
        Save data to save path.
        """
        print(
            f"Process ID: [{os.getpid()}] | Model: {self.model} | File: {self.file} | Saving {len(self.save_data)} items"
        )
        with open(self.save_path, "w", encoding="utf-8") as f:
            json.dump(self.save_data, f, indent=2, ensure_ascii=False)

    def load_exist_data(self, data):
        """
        Load exist data from save path.
        """
        if os.path.exists(self.save_path):
            print(f"Loading exist data from {self.save_path}")
            with open(self.save_path, "r", encoding="utf-8") as f:
                self.save_data = json.load(f)
        ids = [i["id"] for i in self.save_data]
        data = [i for i in data if i["id"] not in ids]
        return data

    @func_set_timeout(10)
    def get_access_token(self):
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

    @func_set_timeout(10)
    def chatgpt_hi_request(
        self,
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
            "Authorization": "Bearer {0}".format(self.get_access_token()),
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

    def gpt_4_complete(self, query, chat_model, **kwargs):
        coun = 0
        while True:
            if coun > 10:
                res = "NO FACTS"
                break
            try:
                res = self.chatgpt_hi_request(query)
                break
            except func_timeout.exceptions.FunctionTimedOut:
                res = "NO FACTS"
                break
            except Exception:
                # print("Exception, retrying...", end="")
                coun += 1
        if res is None:
            res = "NO FACTS"
        return res

    def openai_complete(self, query, chat_model, **kwargs):
        """
        Generate a response for a given query using openai api.
        """
        retry = 0
        while retry < self.max_retry:
            retry += 1
            try:
                if chat_model == "chatgpt":
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo-1106",
                        messages=[{"role": "user", "content": query}],
                        temperature=kwargs["temperature"],
                        top_p=kwargs["top_p"],
                        # greedy search: temperature=0
                        # top_p sampling: temperature=1, top_p=0.5 (0.2, 0.4, 0.6, 0.8, 1.0)
                    )
                elif chat_model.startswith("text-davinci-00"):
                    response = openai.Completion.create(
                        model=chat_model,
                        prompt=query,
                        max_tokens=512,
                        temperature=kwargs["temperature"],
                        top_p=kwargs["top_p"],
                    )
                break
            except openai.error.AuthenticationError as e:
                print("openai.error.AuthenticationError\nRetrying...")
                if "The token quota has been used up" in str(e):
                    print("You exceeded your current quota: %s" % openai.api_key)
                time.sleep(60)
            except openai.error.RateLimitError as e:
                print("openai.error.RateLimitError\nRetrying...")
                time.sleep(60)
            except openai.error.ServiceUnavailableError:
                print("openai.error.ServiceUnavailableError\nRetrying...")
                time.sleep(20)
            except openai.error.Timeout:
                print("openai.error.Timeout\nRetrying...")
                time.sleep(20)
            except openai.error.APIError:
                print("openai.error.APIError\nRetrying...")
                time.sleep(20)
            except openai.error.APIConnectionError:
                print("openai.error.APIConnectionError\nRetrying...")
                time.sleep(20)
            except Exception as e:
                print(f"Error: {str(e)}\nRetrying...")
                time.sleep(10)
        if retry >= self.max_retry:
            raise ValueError("Failed to generate response")
        if chat_model == "chatgpt":
            ans = response["choices"][0]["message"]["content"]
        elif chat_model.startswith("text-davinci-00"):
            ans = response["choices"][0]["text"]
        return ans

    def complete(self, query, chat_model, **kwargs):
        """
        Generate a response for a given query using local models.
        """
        input_ids = self.tokenizer([query]).input_ids
        output_ids = self.llm.generate(
            torch.as_tensor(input_ids).cuda(),
            max_new_tokens=512,
            do_sample=kwargs["do_sample"],
            top_k=kwargs["top_k"],
            top_p=kwargs["top_p"],
            temperature=kwargs["temperature"],
            num_beams=kwargs["num_beams"],
            early_stopping=kwargs["early_stopping"],
            # greedy search: do_sample=False
            # top_p sampling: do_sample=True, top_k=0, top_p=0.5 (0.2, 0.4, 0.6, 0.8, 1.0)
            # top_k sampling: do_sample=True, top_k=50
            # beam search: num_beams=5, early_stopping=True
        )
        output_ids = output_ids[0][len(input_ids[0]) :]
        ans = self.tokenizer.decode(output_ids, skip_special_tokens=True)
        return ans

    def post_process(self, ans, query):
        """
        Remove query and empty lines.
        """
        ans = ans.strip().split("\n")
        ans = "\n".join([_ for _ in ans if _])
        return ans

    def get_template(self, query, chat_model):
        """
        Get prompt template for query.
        """
        if chat_model.startswith("llama-2") and "chat" in chat_model:
            query = f"[INST] <<SYS>>\nYou are a helpful assistant. You are given a user's question, and you MUST give a detailed answer to the user's question.\n<</SYS>>\n\n{query} [/INST]"
        elif chat_model.startswith("alpaca"):
            query = f"Below is an instruction that describes a question. You MUST write a response that appropriately answers the question.\n\n### Instruction:\n{query}\n\n### Response:\n"
        elif chat_model.startswith("vicuna"):
            query = f"In this task, a user will pose a question, and the assistant MUST give a detailed answer to the user's question.\n\nUSER: {query}\nASSISTANT:"
        else:
            # query = f"You MUST give a detailed answer to the following question: {query}"
            query = f"You are a helpful assistant. You are given a user's question, and you MUST give a detailed answer to the user's question.\nquestion: {query}\nanswer:"
        return query

    def generate_response(self, query_lst, **kwargs):
        """
        Generate response for query list.
        """
        if len(query_lst) == 0:
            return
        if self.model.startswith("chatgpt") or self.model.startswith("text-davinci-00"):
            complete_func = self.openai_complete
        else:
            complete_func = self.complete
        if self.model.startswith("llama-2"):
            kwargs["eos_token_id"] = self.tokenizer.eos_token_id
            kwargs["pad_token_id"] = self.tokenizer.eos_token_id
        for i in tqdm(range(len(query_lst)), ncols=100):
            if len(self.save_data) % self.frequency == 0:
                self.save()
            query = query_lst[i]["user_query"]
            query = self.get_template(query, self.model)
            ans = complete_func(query, self.model, **kwargs)
            ans = self.post_process(ans, query)
            query_lst[i][self.model + "_response"] = ans
            self.save_data.append(query_lst[i])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Save data when exit.
        """
        self.save()
        print(f"Process ID: [{os.getpid()}] | Exit")


class Parser(object):
    """
    Parser for arguments.
    """

    def __init__(self, description):
        self.parser = argparse.ArgumentParser(description=description)
        self.file_list = [
            "Bio-Medical",
            "Finance",
            "Science",
            "Education",
            "Open-Domain",
        ]

    def general_args(self):
        """
        Parse arguments for all tasks.
        """
        self.parser.add_argument(
            "--all-files",
            action="store_true",
            help="whether to use all datasets",
        )
        self.parser.add_argument(
            "--file",
            default="Bio-Medical",
            choices=["Bio-Medical", "Finance", "Science", "Education", "Open-Domain"],
            help="dataset to use if not using all datasets",
        )
        self.parser.add_argument(
            "--model",
            default="llama-2-13b-chat-hf",
            choices=[
                "chatgpt",
                "text-davinci-002",
                "text-davinci-003",
                "llama-2-7b-chat-hf",
                "llama-2-13b-chat-hf",
                "alpaca-7b",
                "vicuna-7b",
                "vicuna-13b",
                "llama-7b",
                "claude-1",
                "claude-2",
                # "llama-2-7b-hf",
                # "llama-2-13b-hf",
                # "bloom-7b1",
            ],
            help="chat model to use",
        )
        self.parser.add_argument(
            "--temperature",
            default=1,
            help="sampling temperature to use",
        )
        self.parser.add_argument(
            "--top-p",
            default=1,
            help="only the smallest set of most probable tokens with probabilities\
                that add up to top_p or higher are kept for generation",
        )
        self.parser.add_argument(
            "--early-stopping",
            action="store_true",
            help="the stopping condition for beam-based methods, like beam-search",
        )
        self.parser.add_argument(
            "--do-sample",
            action="store_true",
            help="whether or not to use sampling, use greedy decoding otherwise",
        )
        self.parser.add_argument(
            "--num-beams",
            default=1,
            help="number of beams for beam search. 1 means no beam search",
        )
        self.parser.add_argument(
            "--top-k",
            default=50,
            help="the number of highest probability vocabulary tokens to keep for top-k-filtering",
        )

    def response_args(self):
        """
        Parse arguments for response generation.
        """
        args = self.parser.parse_known_args()[0]
        self.parser.add_argument(
            "--data-dir",
            default="./data/",
            help="data root directory",
        )
        self.parser.add_argument(
            "--save-dir",
            default=f"./response/{args.model}/",
            help="save root directory",
        )
        self.parser.add_argument(
            "--load-in-4bit",
            action="store_true",
            help="whether or not to convert the loaded model into 4bit precision quantized model",
        )
        self.parser.add_argument(
            "--load-in-8bit",
            action="store_true",
            help="whether or not to convert the loaded model into 8bit precision quantized model",
        )

    def fact_args(self):
        """
        Parse arguments for factual statements generation.
        """
        args = self.parser.parse_known_args()[0]
        self.parser.add_argument(
            "--data-dir",
            default=f"./response/{args.model}/",
            help="data root directory",
        )
        self.parser.add_argument(
            "--save-dir",
            default=f"./fact/{args.model}/",
            help="save root directory",
        )
        self.parser.add_argument(
            "--assist-model",
            default="gpt-4",
            choices=[
                "chatgpt",
                "gpt-4",
            ],
            help="facts generation model to use",
        )
        self.parser.add_argument(
            "--prompt-path",
            default="./prompt/generate_fact_ins.txt",
            help="prompt path",
        )

    def judge_args(self):
        """
        Parse arguments for factual statements judgment.
        """
        args = self.parser.parse_known_args()[0]
        self.parser.add_argument(
            "--data-dir",
            default=f"./fact/{args.model}/",
            help="data root directory",
        )
        self.parser.add_argument(
            "--save-dir",
            default=f"./judge/{args.model}/",
            help="save root directory",
        )
        self.parser.add_argument(
            "--assist-model",
            default="gpt-4",
            choices=[
                "chatgpt",
                "gpt-4",
            ],
            help="judge model to use",
        )
        self.parser.add_argument(
            "--prompt-path",
            default="./prompt/determine_truthfulness_ins.txt",
            help="prompt path",
        )

    def parse_args(self):
        """
        Parse all arguments.
        """
        self.args = self.parser.parse_args()

    def transform_args(self):
        """
        Transform some arguments to the correct type.
        """
        self.args.num_beams = int(self.args.num_beams)
        self.args.temperature = float(self.args.temperature)
        self.args.top_k = int(self.args.top_k)
        self.args.top_p = float(self.args.top_p)

    def print_args(self):
        """
        Print all arguments.
        """
        print("Arguments:")
        for arg in vars(self.args):
            print(f"  {arg}: {getattr(self.args, arg)}")


if __name__ == "__main__":
    args_parser = Parser("LLM Response Generation")
    args_parser.general_args()
    args_parser.response_args()
    args_parser.parse_args()
    args_parser.transform_args()
    args_parser.print_args()
    args = args_parser.args
    if args.all_files:
        files = args_parser.file_list
    else:
        files = [args.file]
    bot = Bot(args.model)
    bot.load_model(args.load_in_4bit, args.load_in_8bit)
    for file in files:
        data_path = os.path.join(args.data_dir, f"{file}.json")
        save_path = os.path.join(args.save_dir, f"{file}.json")
        check_exist(args.save_dir)
        with Chatbot(data_path, save_path, args.model, file) as chatbot:
            chatbot.tokenizer = bot.tokenizer
            chatbot.llm = bot.llm
            data = chatbot.load_data(part=0)
            data = chatbot.load_exist_data(data)
            chatbot.generate_response(
                data,
                early_stopping=args.early_stopping,
                do_sample=args.do_sample,
                num_beams=args.num_beams,
                temperature=args.temperature,
                top_k=args.top_k,
                top_p=args.top_p,
            )
