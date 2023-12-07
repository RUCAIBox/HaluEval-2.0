# coding: utf-8
import os
from tqdm import tqdm
from response import Chatbot, Parser, check_exist


class Factbot(Chatbot):
    """
    Chatbot for factual statements generation.
    """

    def __init__(self, data_path, save_path, model, file, assist_model):
        super().__init__(data_path, save_path, model, file)
        self.file = file  # file name
        self.assist_model = assist_model  # facts generation model

    def get_facts_lst(self, ans):
        """
        Get facts list from the assist model's response.
        """
        if "NO FACTS" in ans:
            return []
        try:
            lines = [line.strip() for line in ans.split("\n") if line.strip()]
            if len(lines) == 0:
                print("Empty facts: " + ans)
                return []
            elif len(lines) == 1 and not lines[0].startswith("1."):
                return [lines[0]]
            else:
                return [fact[2:].strip() for fact in lines if fact[2:].strip()]
        except Exception as e:
            print("Error: " + str(e))
            print("Corresponding facts: " + ans)
            return []

    def generate_facts(self, data, prompt, **kwargs):
        """
        Generate facts by the assist model.
        """
        if len(data) == 0:
            return

        if self.assist_model == "gpt-4":
            complete_func = self.gpt_4_complete
        else:
            complete_func = self.openai_complete

        for i in tqdm(range(len(data)), ncols=100):
            if len(self.save_data) % self.frequency == 0:
                self.save()
            query = prompt.format(
                query=data[i]["user_query"], answer=data[i][self.model + "_response"]
            )

            ans = complete_func(query, self.assist_model, **kwargs)
            if ans == "FAILED" or ans == "TIMEOUT":
                continue

            data[i][self.model + "_fact_raw"] = ans
            ans = self.post_process(ans)
            facts = self.get_facts_lst(ans)
            data[i][self.model + "_fact"] = facts
            self.save_data.append(data[i])


if __name__ == "__main__":
    args_parser = Parser("Factual Statements Generation")
    args_parser.general_args()
    args_parser.fact_args()
    args_parser.parse_args()
    args_parser.transform_args()
    args_parser.print_args()
    args = args_parser.args
    if args.all_files:
        files = args_parser.file_list
    else:
        files = [args.file]
    with open(args.prompt_path, "r", encoding="utf-8") as f:
        prompt = f.read()
    left = []  # list of (file, num of unfinished items)
    for file in files:
        data_path = os.path.join(args.data_dir, f"{file}.json")
        save_path = os.path.join(args.save_dir, f"{file}.json")
        check_exist(args.save_dir)
        with Factbot(
            data_path, save_path, args.model, file, args.assist_model
        ) as factbot:
            data = factbot.load_data(part=0)
            data = factbot.load_exist_data(data)
            factbot.generate_facts(
                data,
                prompt,
                temperature=args.temperature,
                top_p=args.top_p,
            )
            left.append((file, factbot.file_length - len(factbot.save_data)))
    # list each file with unfinished items
    print(f"\nProcess ID: [{os.getpid()}] | Left:")
    for file, num in left:
        print(f"    {file}: {num}")
