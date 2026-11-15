// Fixtures copied from contracts/fixtures. Sample shapes only: never present as real data.
import type * as C from "./contract";
import health from "@/mocks/health.json";
import zips from "@/mocks/zips.json";
import zipProfile from "@/mocks/zip_profile.json";
import seriesZori from "@/mocks/zip_series_zori.json";
import seriesZhvi from "@/mocks/zip_series_zhvi.json";
import check from "@/mocks/check.json";
import letter from "@/mocks/letter.json";
import units from "@/mocks/units_search.json";
import evaluate from "@/mocks/listings_evaluate.json";
import rankStarter from "@/mocks/neighborhoods_rank_starter.json";
import rankWealth from "@/mocks/neighborhoods_rank_wealth.json";
import pricePos from "@/mocks/owner_price_position.json";
import analysis from "@/mocks/owner_listing_analysis.json";

import listings from "@/mocks/listings.json";
import listingDetail from "@/mocks/listing_detail.json";
import market from "@/mocks/market.json";
import type { ListingDetail, ListingsResponse, MarketResponse } from "./tracker";

const as = <T,>(x: unknown) => x as T;

export const MOCK = {
  health: as<C.HealthResponse>(health),
  zips: as<C.ZipsResponse>(zips),
  zipProfile: as<C.ZipProfile>(zipProfile),
  seriesZori: as<C.SeriesResponse>(seriesZori),
  seriesZhvi: as<C.SeriesResponse>(seriesZhvi),
  check: as<C.CheckResponse>(check),
  letter: as<C.LetterResponse>(letter),
  listings: as<ListingsResponse>(listings),
  listingDetail: as<ListingDetail>(listingDetail),
  market: as<MarketResponse>(market),
  units: as<C.UnitSearchResponse>(units),
  evaluate: as<C.ListingEvalResponse>(evaluate),
  rankStarter: as<C.RankResponse>(rankStarter),
  rankWealth: as<C.RankResponse>(rankWealth),
  pricePos: as<C.PricePositionResponse>(pricePos),
  analysis: as<C.ListingAnalysisResponse>(analysis),
};
