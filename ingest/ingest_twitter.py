import os
import json
from datetime import datetime, timedelta, timezone
from core.embedder import embed_batch
from core.vectorstore import VectorStore
from core.chunker import chunk_text
from core.database import save_chunks_to_db

# Single reusable vector store instance
db = VectorStore()

def parse_twitter_archive(tweets_js_path: str) -> list[dict]:
    """
    Parses the tweets.js file, filters out retweets, and returns a list of parsed tweets.
    """
    if not os.path.exists(tweets_js_path):
        print(f"Tweets file '{tweets_js_path}' not found.")
        return []
        
    print(f"Reading and parsing '{tweets_js_path}'...")
    try:
        with open(tweets_js_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Locate the JSON array
        first_bracket = content.find("[")
        last_bracket = content.rfind("]")
        
        if first_bracket == -1 or last_bracket == -1:
            print("Invalid tweets.js format: could not locate JSON brackets.")
            return []
            
        json_str = content[first_bracket : last_bracket + 1]
        raw_tweets = json.loads(json_str)
    except Exception as e:
        print(f"Error parsing tweets.js: {e}")
        return []
        
    parsed_tweets = []
    skipped_retweets = 0
    
    # Parse format: Wed Jan 21 14:36:15 +0000 2026
    twitter_date_format = "%a %b %d %H:%M:%S %z %Y"
    
    for item in raw_tweets:
        tweet_data = item.get("tweet", {})
        full_text = tweet_data.get("full_text", "")
        
        # Filter out retweets
        if full_text.startswith("RT @"):
            skipped_retweets += 1
            continue
            
        created_at_str = tweet_data.get("created_at")
        id_str = tweet_data.get("id_str")
        
        if not full_text or not created_at_str or not id_str:
            continue
            
        try:
            dt = datetime.strptime(created_at_str, twitter_date_format)
            parsed_tweets.append({
                "id": id_str,
                "text": full_text,
                "datetime": dt
            })
        except Exception as e:
            print(f"Error parsing date '{created_at_str}' for tweet {id_str}: {e}")
            
    print(f"Loaded {len(parsed_tweets)} tweets (skipped {skipped_retweets} retweets).")
    return parsed_tweets

def group_tweets_by_week(tweets: list[dict]) -> dict:
    """
    Groups tweets by week start (Monday).
    Returns a dictionary of week_start_date_str -> list of tweets.
    """
    grouped = {}
    for tweet in tweets:
        dt = tweet["datetime"]
        # Calculate Monday of the week
        week_start = dt.date() - timedelta(days=dt.weekday())
        week_start_str = week_start.strftime("%Y-%m-%d")
        
        if week_start_str not in grouped:
            grouped[week_start_str] = []
        grouped[week_start_str].append(tweet)
        
    return grouped

def ingest_twitter(tweets_dir: str = "Tweets", batch_size: int = 10):
    """
    Main function to ingest tweets from tweets.js and index them.
    """
    tweets_js_path = os.path.join(tweets_dir, "tweets.js")
    tweets = parse_twitter_archive(tweets_js_path)
    if not tweets:
        return
        
    grouped = group_tweets_by_week(tweets)
    print(f"Grouped tweets into {len(grouped)} weeks.")
    
    # Sort and format all weekly documents
    weekly_docs = []
    for week_start_str, week_tweets in sorted(grouped.items()):
        # Sort tweets of the week chronologically
        week_tweets.sort(key=lambda x: x["datetime"])
        
        # Calculate date range
        start_date = datetime.strptime(week_start_str, "%Y-%m-%d").date()
        end_date = start_date + timedelta(days=6)
        date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        
        # Format weekly document
        doc_lines = [f"### Weekly Tweets: {date_range}\n"]
        tweet_ids_list = []
        
        for t in week_tweets:
            time_str = t["datetime"].strftime("%Y-%m-%d %H:%M:%S")
            doc_lines.append(f"- [{time_str}] {t['text']}")
            tweet_ids_list.append(t["id"])
            
        doc_text = "\n".join(doc_lines)
        tweet_ids_str = ",".join(tweet_ids_list)
        
        weekly_docs.append({
            "id": f"twitter_{week_start_str}",
            "text": doc_text,
            "metadata": {
                "source": "twitter",
                "date_range": date_range,
                "tweet_ids": tweet_ids_str
            }
        })
        
    all_chunks = []
    for doc in weekly_docs:
        chunks = chunk_text(
            text=doc["text"],
            source_id=doc["id"],
            metadata=doc["metadata"]
        )
        all_chunks.extend(chunks)
        
    total_chunks = len(all_chunks)
    print(f"Starting batch embedding of {total_chunks} tweet chunks...")
    
    success_count = 0
    
    for i in range(0, total_chunks, batch_size):
        batch = all_chunks[i : i + batch_size]
        batch_texts = [chunk["text"] for chunk in batch]
        
        try:
            # Generate embeddings in batch
            batch_embeddings = embed_batch(batch_texts)
            
            # Prepare batch for ChromaDB
            texts = []
            metadatas = []
            ids = []
            embeddings = []
            
            for j, chunk in enumerate(batch):
                if j < len(batch_embeddings):
                    texts.append(chunk["text"])
                    metadatas.append(chunk["metadata"])
                    ids.append(f"{chunk['source_id']}_chunk_{chunk['chunk_index']}")
                    embeddings.append(batch_embeddings[j])
                    success_count += 1
                    
            if ids:
                db.add_documents(texts, metadatas, ids, embeddings)
                print(f"Indexed {success_count}/{total_chunks} tweet chunks...")
        except Exception as e:
            print(f"Failed to embed batch starting at index {i}: {e}")
            
    print(f"Successfully finished Twitter ingestion. Indexed {success_count}/{total_chunks} chunks.")
    print("Syncing Twitter chunks to SQLite database...")
    save_chunks_to_db(all_chunks)
    print("Twitter chunks synced to SQLite.")

if __name__ == "__main__":
    ingest_twitter()
