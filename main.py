import os
import time
import random
from dotenv import load_dotenv

import numpy as np
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from bs4 import BeautifulSoup

import praw
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

def get_listing(page_depth):
    '''
    page_depth must be an integer value. For this prototype version, we recommend that you scroll down all the way through the bottom of ArtNet's listings to see how many pages there are when you run this code.
    '''
    art_list = []

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36"
    ]

    for n in range(1,page_depth+1):
        # Rotate user-agent
        user_agent = random.choice(user_agents)
        # Set up options to use a custom User-Agent
        chrome_options = Options()
        chrome_options.add_argument(f"user-agent={user_agent}")

        # Set up the WebDriver (in this case for Chrome)
        # You need to specify the path to your ChromeDriver
        chrome_driver_path = r"/Users/ianchang/Library/Mobile Documents/com~apple~CloudDocs/1. Project/chromedriver-mac-x64/chromedriver"

        # Initialize the WebDriver
        service = Service(chrome_driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Open the website
        url = f'https://www.artnet.com/auctions/all-artworks/{n}'
        driver.get(url)

        # Parse the page source using BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Extract the artwork data 
        artworks = soup.find_all('div', class_='details')
        art_list += artworks 

        # Close the WebDriver after scraping
        driver.quit()
        
        # Introduce a random delay to avoid bot detection (2-6 seconds)
        time.sleep(random.uniform(2, 6))

    return art_list

def get_df_of_listings(page_depth):

    art_list = get_listing(page_depth)

    art_data = []

    for index, art in enumerate(art_list, 1):
        artist_element = art.find("li", class_ = "ng-binding")
        if artist_element:
            artist_name = artist_element.text.strip()
        else:
            print(f"Missing artist name")
            continue

        piece_element = art.find("em", class_ = "ng-binding")
        if piece_element:
            piece_name = piece_element.text.strip()
        else:
            print(f"Missing piece name")
            continue

        price_element = art.find('li', class_="ng-binding ng-scope").text.strip()
        if "Bids" in price_element:
            price_text, bid_text = price_element.split(" (")
            price, currency = price_text.split(" ")
            price = float(price.replace(",", ""))
            bids = int(bid_text.replace("Bids)",""))
        elif "Bid" in price_element:
            price_text, bid_text = price_element.split(" (")
            price, currency = price_text.split(" ")
            price = float(price.replace(",", ""))
            bids = 1
        else:
            price_range, currency = price_element.split(" ")
            lower_bound, upper_bound = price_range.split("—")
            lower_bound = float(lower_bound.replace(",",""))
            upper_bound = float(upper_bound.replace(",",""))
            price = float(np.mean([lower_bound, upper_bound]))
            bids = 0

        expiration_element = art.find('li', {"ng-class": "{'red' : brick.Remaining.Days <= 0}"}).text.strip()
        if expiration_element:
            expiration, daysText, remainingText = expiration_element.split(" ")
            expiration = int(expiration)
        
        # print(artist_name, piece_name, price, currency, bids) -> to see if it all turned out okay
        
        art_data.append({
            "Artist": artist_name,
            "Name of Piece": piece_name,
            "Current Price": price,
            "Currency": currency,
            "Num of Bids": bids,
            "Days Left": expiration
            })

    art_df = pd.DataFrame(art_data)

    art_df = art_df.sort_values(by=["Days Left"], ascending= True).reset_index(drop=True)

    return art_df

def get_unique_artists(artwork_dataframe):
    
    unique_artists = []

    for n in range(0,len(artwork_dataframe.Artist.unique())):
        name = artwork_dataframe.Artist.unique()[n]
        unique_artists.append(name)

    return unique_artists

# Reddit r/Art portion:

# Load environment variables
load_dotenv()

reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent=os.getenv('REDDIT_USER_AGENT'),
    username=os.getenv('REDDIT_USERNAME'),
    password=os.getenv('REDDIT_PASSWORD')
)

def get_sentiment_score(artist_name):

    commentList = []
    submissions = reddit.subreddit("Art").search(f"{artist_name.lower()}", sort = "relevance")
    
    for submission in submissions:
        submission.comments.replace_more(limit=0)  # Expand the "load more" comments
        for top_level_comment in submission.comments:
            
            # Check if comment has a body (not deleted or removed)
            if top_level_comment.body:
                commentList.append(top_level_comment.body.lower())

    sentiment_analyzer = SentimentIntensityAnalyzer()

    compound_scores = []
    
    for index, comment in enumerate(commentList, 1):
        vs = sentiment_analyzer.polarity_scores(comment)
        compound_scores.append(vs["compound"])
    
    if len(compound_scores) > 0:
        mean_score = float(np.mean(compound_scores))
    elif len(compound_scores) == 0:
        mean_score = 0.0
    return mean_score

def get_artist_score_df(artist_names_list):
    scores_list = []

    for name in artist_names_list:
        score = get_sentiment_score(name)
        scores_list.append({"Artist": name, "Sentiment Score": score})
    
    scores_df = pd.DataFrame(scores_list)
    
    return scores_df

current_listings_df = get_df_of_listings(4)
current_artists_list = get_unique_artists(current_listings_df)
current_scores_df = get_artist_score_df(current_artists_list)

def get_final_df(df_of_listings, df_of_scores):
    merged_df = pd.merge(df_of_listings, df_of_scores, how="left", left_on="Artist", right_on="Artist")
    for index, row in merged_df.iterrows():
        if row["Sentiment Score"] > 0.1:
            merged_df.loc[index, "Bid Action"] = "Bid Higher"
        else:
            merged_df.loc[index, "Bid Action"] = "Do Not Bid"
    
    return merged_df

recs_df = get_final_df(current_listings_df, current_scores_df)
print(recs_df)