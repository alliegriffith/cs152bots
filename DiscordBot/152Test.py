import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch.nn as nn
import pandas as pd

class Critic(nn.Module):
    def __init__(self, hidden_size):
        super().__init__()
        self.critic = nn.Sequential(
            nn.Linear(hidden_size, 2048),
            nn.ReLU(),
            nn.Linear(2048, 2048),
            nn.ReLU(),
            nn.Linear(2048, 1)
        )

    def forward(self, hidden_vec):
        return self.critic(hidden_vec)   # returns shape [batch_size, 1]


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


base_model_name = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    output_hidden_states=True
).to(device)
model.eval()

tokenizer = AutoTokenizer.from_pretrained(
    base_model_name,
    padding_side="left"
)

# create new critic and load trained values into it
hidden_size = model.config.hidden_size 
print("hidden size of tiny llama:", hidden_size)
critic = Critic(hidden_size).to(device)
critic_load_path = "critic_sextortion.pt"
critic.load_state_dict(torch.load(critic_load_path, map_location=device))
critic.eval()
print(f"Loaded critic weights from {critic_load_path}")

# use critic to predict if message is from perpetrator of sextortion
def predict_sextortion(text: str) -> float:
    """
    Returns a float in [0,1], the critic’s predicted probability
    that ‘text’ is a sextortion message.
    """
    # tokenize message
    toks = tokenizer(
        text,
        return_tensors="pt",
        padding=True,
        truncation=True
    )
    
    input_ids      = toks["input_ids"].to(device)      # [1, seq_len]
    attention_mask = toks["attention_mask"].to(device)

    # forward pass through TinyLlama (to get hidden states)
    with torch.no_grad():
        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            return_dict=True
        )
        # take the last hidden state for the last token (bc tinyllama is causal, reps all previous tokens)
        last_token_hidden = outputs.hidden_states[-1][:, -1, :]       # [1, seq_len, hidden_size]
        

        # forward pass through critic → raw score
        score = critic(last_token_hidden).view(-1)                # [1]

        # convert to prob via sigmoid
        prob = torch.sigmoid(score).item()             # Python float in [0,1]
        
        return prob

def eval():
    # Test time!
    # load test data
    test_df = pd.read_csv("/home/allie11/baselines/data/sextortion_test.csv")
    # set threshold! determines balance between false positive and false negative
    threshold = 0.5

    false_pos = 0.0 # we labeled it positive but it really was negative
    false_neg = 0.0 # we labeled it negative but it really was positive
    true_pos = 0.0 # correctly predict positive
    true_neg = 0.0 # correctly predict negative
    accuracy = 0.0 # correct labels / total lables (tp + tn / all)
    num_neg = 0.0
    num_pos = 0.0

    for i in range(len(test_df)):
        message = test_df.loc[i]["text"]
        label = test_df.loc[i]["label"]
        score = predict_sextortion(message)
        print(f"Text: {message}\n→ Sextortion probability: {score:.4f}\n")
        
        if score > threshold:
            # predicted positive
            if label == "sextortion":
                num_pos += 1
                # correct label! (true pos)
                true_pos += 1
            else:
                # incorrect label (false positive)
                false_pos += 1
        else:
            # predicted negative label
            if label == "not_sextortion":
                num_neg += 1
                # correct label! (true neg)
                true_neg += 1
            else:
                # incorrect label
                false_neg += 1
                
    total = len(test_df)   
    false_neg_per = false_neg / num_pos
    true_neg_per = true_neg / num_neg 
    false_pos_per = false_pos / num_neg 
    true_pos_per = true_pos / num_pos
    accuracy_per = (true_pos + true_neg) / total

    print("Eval results:")
    print("false neg / miss rate: ", false_neg_per)
    print("true neg:", true_neg_per)
    print("false pos", false_pos_per)
    print("true pos", true_pos_per)
    print("total accuracy", accuracy_per)

def manual_test(message):
    score = predict_sextortion(message)
    print(f"Text: {message}\n→ Sextortion probability: {score:.4f}\n")

if __name__ == "__main__":
    
    #eval() # tells us we are accurate 100% of the time
    #message = "Send me nudes or I will..." # correct (0.5652)
    #message = "You are trapped. You have to do what I say." # correct (0.6849)
    #message = "Hi! I think you are cute. Can you send me nudes?" # correct (0.2100)
    #message = "If you don't send me more content I will tell your parents what you have done" # incorrect? (0.4965)
    # message = "You have to send me $500 by tonight" # correct (0.6583)
    # message2 = "Let's move to a different platform. Do you have WhatsApp?" # missed warning sign (0.1144)
    # message3 = "If you don't send me 500$ everyone at your school will know" # barely missed (0.4853)
    # message = "Hey babe! Can you send me some nudes please?" # correct (0.2814)
    # message2 = "Hey, did you send your nudes to someone? I have them." # correct (0.4086)
    # message3 = "Hey, did you send your nudes to someone? I have them and if you send me more I won't share them with anyone" # correct (0.5713)
    
    # message = "Hey babe! Can you send me some nudes please?" 
    # manual_test(message)
    
    # message2 = "Hey, did you send your nudes to someone? I have them." 
    # manual_test(message2)
    
    # message3 = "Hey, did you send your nudes to someone? I have them and if you send me more I won't share them with anyone" 
    # manual_test(message3)
    
    # eval with 0.4 - still 100% accurate
    eval()
    