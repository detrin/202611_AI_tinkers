"""Composition root: the only place that knows concrete adapters."""
from dataclasses import dataclass

from .config import Settings
from .ports import (AestheticSource, CalendarProvider, ChatModel, Database, Executor, HourlyWeatherProvider,
                    ImageFetcher, ImageStore, PinSource, ProductSource, SocialSource, StructuredModel,
                    TrendSource, VenueProvider, WeatherProvider)
from .services.catalog import CatalogService
from .services.good_enough import GoodEnoughService
from .services.feedback import ProductFeedbackService
from .services.images import ImageService
from .services.imports import ImportService
from .services.inspirations import InspirationService
from .services.jobs import JobService
from .services.links import LinkService
from .services.outfits import OutfitService
from .services.preferences import PreferenceService
from .services.profiles import ProfileService
from .services.recommendations import RecommendationService
from .services.style_library import StyleLibraryService
from .services.style_recs import StyleRecommendationService
from .services.styles import StyleService
from .services.taste import TasteService
from .services.trends import TrendService
from .services.stylist import Stylist
from .services.today import TodayService
from .services.users import UserService
from .services.wardrobe import WardrobeService


@dataclass(frozen=True)
class Container:
    images: ImageService
    users: UserService
    wardrobe: WardrobeService
    inspirations: InspirationService
    styles: StyleService
    preferences: PreferenceService
    profiles: ProfileService
    recommendations: RecommendationService
    feedback: ProductFeedbackService
    imports: ImportService
    links: LinkService
    outfits: OutfitService
    taste: TasteService
    library: StyleLibraryService
    trends: TrendService
    style_recs: StyleRecommendationService
    jobs: JobService
    weather: WeatherProvider
    good_enough: GoodEnoughService
    today: TodayService
    today_api_token: str | None


def build_services(*, db: Database, store: ImageStore, fetcher: ImageFetcher, chat: ChatModel, pins: PinSource,
                   products: ProductSource, social: SocialSource, weather: WeatherProvider,
                   taste_model: StructuredModel, aesthetics: AestheticSource, trends: TrendSource,
                   executor: Executor, calendar: CalendarProvider | None = None,
                   hourly_weather: HourlyWeatherProvider | None = None, venue: VenueProvider | None = None,
                   timezone: str = "Europe/Prague", today_api_token: str | None = None) -> Container:
    stylist = Stylist(chat)
    images = ImageService(db, store, fetcher)
    users = UserService(db, images, stylist)
    wardrobe = WardrobeService(db, users, images, stylist)
    styles = StyleService(db, pins, stylist)
    prefs = PreferenceService(db)
    inspirations = InspirationService(db, users, images, prefs, stylist)
    profiles = ProfileService(db, users, wardrobe, inspirations, styles, prefs, stylist)
    catalog = CatalogService(db, products)
    outfits = OutfitService(db, users, wardrobe, images, weather, stylist)
    library = StyleLibraryService(db, aesthetics, taste_model)
    return Container(
        images=images, users=users, wardrobe=wardrobe, inspirations=inspirations, styles=styles, preferences=prefs,
        profiles=profiles,
        recommendations=RecommendationService(db, catalog, profiles, wardrobe, stylist),
        feedback=ProductFeedbackService(db, wardrobe),
        imports=ImportService(db, users, images, wardrobe, catalog, social, stylist),
        links=LinkService(db, users, catalog, profiles, wardrobe, stylist),
        outfits=outfits,
        taste=TasteService(db, users, wardrobe, inspirations, prefs, styles, taste_model),
        library=library, trends=TrendService(db, trends, library, taste_model),
        style_recs=StyleRecommendationService(db, users, wardrobe, inspirations, library),
        jobs=JobService(db, executor), weather=weather,
        good_enough=GoodEnoughService(users, wardrobe, weather, stylist),
        today=TodayService(users, outfits, stylist, calendar, hourly_weather, venue, timezone),
        today_api_token=today_api_token,
    )


def _chat(s: Settings, cls):
    from .config import LLM_PROVIDERS
    base_url, _, _, _, text_order = LLM_PROVIDERS[s.llm_provider]
    return cls.create(base_url, s.llm_key, s.vision_model, s.text_model, {s.text_model: text_order} if text_order else None)


def build_container(settings: Settings | None = None) -> Container:
    from apify_client import ApifyClient
    from supabase import create_client

    from .adapters.apify import ApifyInstagramSource, ApifyPinSource, ApifyProductSource, ApifyRunner, ApifyTrendSource
    from .adapters.apify_mcp import ApifyVenueLookup
    from .adapters.calendar import ICalCalendar
    from .adapters.claude_cli import ClaudeCLI
    from .adapters.executors import ThreadExecutor
    from .adapters.fandom import FandomAestheticSource
    from .adapters.openai_chat import OpenAIChat
    from .adapters.html import FallbackProductSource, HtmlProductSource
    from .adapters.supabase import SupabaseDatabase, SupabaseImageStore
    from .adapters.web import HttpImageFetcher, OpenMeteoWeather

    s = settings or Settings.load()
    client = create_client(s.supabase_url, s.supabase_key)
    runner = ApifyRunner(ApifyClient(s.apify_token))
    weather = OpenMeteoWeather()
    calendar = (
        ICalCalendar(s.calendar_ics_url, s.calendar_demo_user_id)
        if s.calendar_ics_url and s.calendar_demo_user_id else None
    )
    return build_services(
        db=SupabaseDatabase(client), store=SupabaseImageStore(client, s.bucket, s.signed_url_ttl),
        fetcher=HttpImageFetcher(), chat=_chat(s, OpenAIChat),
        pins=ApifyPinSource(runner), products=FallbackProductSource(HtmlProductSource(), ApifyProductSource(runner)),
        social=ApifyInstagramSource(runner), weather=weather, hourly_weather=weather,
        taste_model=ClaudeCLI(s.taste_model),
        aesthetics=FandomAestheticSource(), trends=ApifyTrendSource(runner),
        executor=ThreadExecutor(s.job_workers),
        calendar=calendar, venue=ApifyVenueLookup(s.apify_token) if s.apify_venue_lookup else None,
        timezone=s.outfit_timezone, today_api_token=s.today_api_token,
    )
