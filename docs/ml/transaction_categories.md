# Transaction categories

Taxonomy version: `transaction-categories-v1`. The learned models predict the
12 expense labels below. Use the purchase purpose when the text supports it;
otherwise keep the item for review. `other` means the available text does not
support a more specific expense category.

| Label | Use for | Common boundary |
|---|---|---|
| `groceries` | Food and household consumables for home | Cafes and bakeries are `dining` |
| `dining` | Restaurants, cafes, bakeries, delivery | Supermarkets are `groceries` |
| `transport` | Transit, taxis, fuel, parking | Flights and hotels are `travel` |
| `housing` | Rent and property management | Energy and internet are `utilities` |
| `utilities` | Energy, water, internet, phone | Devices bought outright are `shopping` |
| `healthcare` | Treatment, pharmacy, dental care | Insurance premiums are `insurance` |
| `shopping` | Retail goods and personal care | Medical services are `healthcare` |
| `entertainment` | Streaming, games, cinema, events | Restaurants remain `dining` |
| `travel` | Flights, hotels, holiday bookings | Routine transit is `transport` |
| `insurance` | Insurance premiums | Treatment is `healthcare` |
| `education` | Tuition, courses, explicit learning material | General bookstore purchases are `shopping` |
| `other` | Expense with no defensible specific label | Ambiguous examples need review |

The product also has `income`, `investments`, `fees`, `taxes`, `savings`, and
`cash`. These are outside expense-model training. Clear direction-aware text
rules can assign them; unmatched inflows and contradictory phrases go to review.
Transfers remain outside this version because their purpose often needs account
context. Changing label meanings requires a new taxonomy version and evaluation.
