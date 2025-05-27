# Install transformers from source - only needed for versions <= v4.34
# pip install git+https://github.com/huggingface/transformers.git
# pip install accelerate

import torch
from transformers import pipeline

# example messages
# "If you don't send me $100 I am sending your nudes to your family.
pipe = pipeline("text-generation", model="TinyLlama/TinyLlama-1.1B-Chat-v1.0", torch_dtype=torch.bfloat16, device_map="auto")

# We use the tokenizer's chat template to format each message - see https://huggingface.co/docs/transformers/main/en/chat_templating
messages = [
    {
        "role": "system",
        "content": "only return a single numerical value from 0-1 on how likely the following message was sent from a perpetrator of sextortion (.99 = 99'%' confident it is an instance of sextortion, 0.01 = 1%'s confident it is not an instance of sextortion, 0.5 = 50%'s confident it is an instance of sextortion"
    },
    {"role": "user", "content": "Hey, how are you."},
]

prompt = pipe.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
outputs = pipe(prompt, max_new_tokens=256, do_sample=True, temperature=0.7, top_k=50, top_p=0.95)
print(outputs[0]["generated_text"])


# # try with llama 3 -3B
# import torch
# from transformers import pipeline

# model_id = "meta-llama/Llama-3.2-3B"

# pipe = pipeline(
#     "text-generation", 
#     model=model_id, 
#     torch_dtype=torch.bfloat16, 
#     device_map="cuda:1"
# )

# pipe("Give a single number (from 0-100) on your percent confidence that the following message in quotes sent by a perpetrator of sextortion: 'if you do not give my $100 I am sending your nudes to your family'")
