# Dummy Schema 
This project uses a small dummy schema with 3 related tables that require JOINs to answer cross-table questions.

## Users
- user_id: INTEGER PRIMARY KEY
- name: TEXT
- email: TEXT

## Orders
- order_id: INTEGER PRIMARY KEY
- user_id: INTEGER (FK -> Users.user_id)
- product_id: INTEGER (FK -> Products.product_id)
- quantity: INTEGER
- order_date: DATE

## Products
- product_id: INTEGER PRIMARY KEY
- name: TEXT

- price: DECIMAL
