# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow
[SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-08-31

### Added

- Initial release. MCP server for the ozon.ru buyer account over the internal
  composer-api / entrypoint-api.
- **Orders**: active and completed (archive) orders with status, pickup point,
  delivery ETA and date; per-order products; date-range filter.
- **Purchase history**: full purchased-items list and fast server-side search.
- **Catalog**: search with sort and facet filters, category browsing, product
  cards (variants, price, characteristics, gallery photos), descriptions,
  reviews, delivery estimate, "find cheaper".
- **Cart / favorites / collections / wishlists**: read and (gated) mutate.
- **Finance**: Ozon Card balance and points by type (Ozon points, miles, WOW
  points, seller bonuses).
- **Price monitoring** for favorites.
- Browser-bootstrapped session with direct `curl_cffi` HTTP transport and
  automatic token refresh.
