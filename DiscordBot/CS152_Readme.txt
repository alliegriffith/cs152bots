Updated README for CS152 Final Project

- This Github Repo contains the code for Team 11's Project to mitigate Sextortion on Discord through
manual and automated reporting flows

152Test.py : Code to evaluate trained neural network classifier automatically (on test split of data)
              and manually. It also contains the function predict_sextortion() which runs an 
              example through the bot and returns the probability of sextortion.

152Train.py: Code to train automatic bot on training split of data.

bot.py and report.py: Code that runs the moderation bot on Discord.

critic_sextortion.pt : trained classifier neural network weights.

Final Milestone Video Demo: https://github.com/alliegriffith/cs152bots/blob/main/DiscordBot/team11_bot_demo.mp4

Final Milestone Poster: https://github.com/alliegriffith/cs152bots/blob/main/DiscordBot/team11_poster.pdf