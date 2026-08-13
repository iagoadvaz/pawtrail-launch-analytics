# Olist reference distributions

This project borrows two *statistical distributions* from the real, public
[Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(Kaggle) to make PawTrail's synthetic kit-delivery logistics and geography
realistic. No Olist customer, order, or product identity is reused — only
the empirical shape of delivery durations and regional concentration.

Two deliberate transformations are applied, both documented in the design
spec §4:

- **Delivery duration, not delay-vs-estimate.** Olist's estimated delivery
  dates are heavily padded, so `actual - estimated` is centred around 10-12
  days *early* and does not describe how long a shipment took. We use
  purchase-to-delivery duration instead, then rescale it to a subscription-kit
  fulfilment range (see `TARGET_MEDIAN_FULFILLMENT_DAYS` in the generator).
- **Regional shape mapped onto a US market.** PawTrail is priced in USD, so
  Brazilian state codes would be internally inconsistent. We keep Olist's
  *concentration curve* (one dominant region, a long tail) and relabel the
  top N regions onto US state codes by rank. The shape is real; the labels
  are not, and nothing is claimed about the US market itself.

## To regenerate the reference files

1. Download the dataset via the Kaggle CLI (requires a free Kaggle account
   and API token):

   ```bash
   kaggle datasets download -d olistbr/brazilian-ecommerce -p data/olist_reference/raw --unzip
   ```

2. Run the extraction script:

   ```bash
   python data/olist_reference/fetch_olist_reference_distributions.py
   ```

This writes `reference_delivery_durations.csv` and
`reference_state_distribution.csv` into this directory. Those two small
files are committed to the repo; the raw Olist download itself is not
(see `.gitignore`).
