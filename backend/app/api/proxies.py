from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select, update

from ..dependencies import SecretBoxDep, SessionDep
from ..models import Subscription, SubscriptionProxy, UpstreamProxy
from ..schemas import ProxyCreate, ProxyResponse, ProxyUpdate
from ..services.proxies import proxy_response, validate_proxy_url

router = APIRouter(prefix="/proxies", tags=["proxies"])


@router.get("")
async def list_proxies(
    session: SessionDep,
    secret_box: SecretBoxDep,
) -> list[ProxyResponse]:
    proxies = (
        await session.scalars(select(UpstreamProxy).order_by(UpstreamProxy.name))
    ).all()
    return [proxy_response(proxy, secret_box) for proxy in proxies]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_proxy(
    payload: ProxyCreate,
    session: SessionDep,
    secret_box: SecretBoxDep,
) -> ProxyResponse:
    try:
        validate_proxy_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    proxy = UpstreamProxy(
        name=payload.name, url_ciphertext=secret_box.encrypt(payload.url)
    )
    session.add(proxy)
    await session.commit()
    return proxy_response(proxy, secret_box)


@router.patch("/{proxy_id}")
async def update_proxy(
    proxy_id: str,
    payload: ProxyUpdate,
    session: SessionDep,
    secret_box: SecretBoxDep,
) -> ProxyResponse:
    proxy = await session.get(UpstreamProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    if payload.name is not None:
        proxy.name = payload.name
    if payload.url is not None:
        try:
            validate_proxy_url(payload.url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        subscription_ids = select(SubscriptionProxy.subscription_id).where(
            SubscriptionProxy.proxy_id == proxy_id
        )
        await session.execute(
            update(Subscription)
            .where(Subscription.id.in_(subscription_ids))
            .values(status="never", last_error=None, updated_at=datetime.now(UTC))
        )
        proxy.url_ciphertext = secret_box.encrypt(payload.url)
    await session.commit()
    return proxy_response(proxy, secret_box)


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy(proxy_id: str, session: SessionDep) -> Response:
    proxy = await session.get(UpstreamProxy, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="Proxy not found")
    subscription_ids = select(SubscriptionProxy.subscription_id).where(
        SubscriptionProxy.proxy_id == proxy_id
    )
    await session.execute(
        update(Subscription)
        .where(Subscription.id.in_(subscription_ids))
        .values(status="never", last_error=None, updated_at=datetime.now(UTC))
    )
    await session.delete(proxy)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
