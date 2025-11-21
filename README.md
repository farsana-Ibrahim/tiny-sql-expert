🌟 Tiny SQL Expert — English to SQL using Small Language Models (<4B)

This project is my submission for:

AI/ML & Automation Intern – Option 3: Tiny SQL Expert (SLM Optimization)
It demonstrates the ability to use small language models, prompt engineering, and a self-correction loop to convert natural language into SQL.


---

🚀 Overview

The goal of this project is to translate natural language questions into valid SQL queries using a small (<4B) local language model such as:

TinyLlama/TinyLlama-1.1B-Chat-v1.0

bigscience/bloom-3b

phi-2

qwen1.5-1.8b


The program includes:

✓ A database schema
✓ Few-shot prompt
✓ SQL validation rules
✓ A retry loop (self-correction mechanism)
✓ Final output = pure SQL only


---

🧠 Features

✔ Uses ONLY small LLMs (<4B parameters)

✔ Implements strict SQL validation

Catches:

missing SELECT / FROM

invalid tables

forbidden keywords

syntax errors (via sqlparse)


✔ Self-correction loop

If the model’s first query is wrong:

1. The validator reports errors


2. Errors + previous SQL are fed back into model


3. Model generates a corrected SQL


4. Loop continues until success OR max retries



✔ Output is only the SQL statement

All logs go to STDERR so SQL stays clean.


---

🗂️ Schema Used

The schema contains 3 related tables requiring JOIN operations.

Users(user_id, name, email)
Orders(order_id, user_id, product_id, quantity, order_date)
Products(product_id, name, price)


---

📦 Installation

1️⃣ Create and activate virtual environment (optional)

python -m venv venv
source venv/bin/activate     (Linux/Mac)
venv\Scripts\activate        (Windows)

2️⃣ Install dependencies

pip install -r requirements.txt


---

▶️ How to Run

Basic usage:

python app.py "YOUR QUESTION HERE" --model MODEL_NAME

Example 1:

python app.py "List all users who placed an order." --model TinyLlama/TinyLlama-1.1B-Chat-v1.0

Example 2:

python app.py "Find the product name ordered by each user." --model TinyLlama/TinyLlama-1.1B-Chat-v1.0

Example 3:

python app.py "Show order id, user name and product name for all orders." --model bigscience/bloom-3b

Example 4:

python app.py "What are the top 5 most expensive products?" --model TinyLlama/TinyLlama-1.1B-Chat-v1.0


---

🎯 Sample Output

SELECT u.name, u.email
FROM Users u
JOIN Orders o ON u.user_id = o.user_id;

No additional text is printed — only SQL.


---

🔁 Self-Correction Loop (Example)

The model often fails in Attempt 1:

;

Validator errors:

Missing SELECT

No known schema tables

Invalid SQL


Attempt 2:

SELECT u.name, u.email
FROM Users u
JOIN Orders o ON u.user_id = o.user_id;

Validation: PASSED ✔


---

📹 Demo Video

(Add your Loom / YouTube link here)

https://www.loom.com/your-demo-link


---

📁 Repository Structure

tiny-sql-expert/
│── app.py
│── README.md
│── requirements.txt
│── schema.md          (optional documentation)
│── screenshots/        (optional)


---

🧪 Testing Tips

Try running different questions:

“Show users and the products they ordered.”

“Find each user and their total order count.”

“List all orders placed in 2023.”

“List product name, user name, and quantity ordered.”



---

💡 Technologies Used

Python 3.10+

HuggingFace Transformers

TinyLlama / Bloom-3B

SQLParse (syntax validation)

Regex-based guards

Prompt Engineering (few-shot)



---

🙋‍♀️ Author

Farsana Ibrahim
