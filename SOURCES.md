# Official sources and reuse boundary

- [NOAA ISD product](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database): ISD-Lite is the documented reduced hourly product.
- [Official service-change notice](https://www.nesdis.noaa.gov/news/service-location-change-integrated-surface-data-global-hourly): original endpoints retired; NODD archive remains; ISD stopped updating after24August2025. This study uses completed historical years, not current weather or latest GHCNh data.
- [NODD/AWS registry](https://registry.opendata.aws/noaa-isd/): public no-account access and attributed reuse; no NOAA endorsement or claim that derivatives are unchanged NOAA data.
- [Official format](https://noaa-isd-pds.s3.amazonaws.com/isd-lite/isd-lite-format.txt) and [technical document](https://noaa-isd-pds.s3.amazonaws.com/isd-lite/isd-lite-technical-document.txt): fixed-width fields; tenths degreeC and -9999 sentinel; near-hour capture/duplicate selection; no additional Lite QC or retained full flags; unsuitable when exact observation timing/density is critical. These documents are read and linked, not republished.
- [Official station history](https://noaa-isd-pds.s3.amazonaws.com/isd-history.csv): fixed airport identifiers, names and period-of-record metadata. [Original ISD format](https://noaa-isd-pds.s3.amazonaws.com/isd-format-document.pdf) defines inherited time/temperature fields.

This is a bounded empirical tail and aggregation comparison using established arithmetic and whole-year resampling. No new estimator, exhaustive novelty review, fitted extreme-value model, continuous physical exposure, facility/product validation or prospective climate claim. All analytical thresholds are illustrative and fixed before data outcomes.
