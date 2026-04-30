from typing import Callable

from app.domain.models import ProviderName
from app.providers.azure_di_gpt import make_azure_di_gpt
from app.providers.base import OCRProvider
from app.providers.mistral import make_mistral_2505, make_mistral_2512


_FACTORIES: dict[ProviderName, Callable[[], OCRProvider]] = {
    ProviderName.MISTRAL_2505: make_mistral_2505,
    ProviderName.MISTRAL_2512: make_mistral_2512,
    ProviderName.AZURE_DI_GPT: make_azure_di_gpt,
}


def get_provider(name: ProviderName) -> OCRProvider:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ValueError(f"Unknown provider: {name}")
    return factory()


def list_provider_names() -> list[ProviderName]:
    return list(_FACTORIES.keys())
