from __future__ import annotations

import os
import random
import time
from concurrent import futures

import grpc

import payments_pb2
import payments_pb2_grpc


def authorize_payment(request: payments_pb2.CreatePaymentRequest) -> payments_pb2.CreatePaymentResponse:
    if not request.customer_id or request.amount <= 0 or not request.currency:
        return payments_pb2.CreatePaymentResponse(
            payment_id="",
            status="rejected_missing_required_fields",
        )
    return payments_pb2.CreatePaymentResponse(
        payment_id=f"pay_grpc_{int(time.time() * 1000)}",
        status="authorized",
    )


class PaymentsService(payments_pb2_grpc.PaymentsServicer):
    def CreatePayment(self, request: payments_pb2.CreatePaymentRequest, context: grpc.ServicerContext):
        base_ms = float(os.getenv("DEMO_BASE_LATENCY_MS", "15"))
        jitter_ms = float(os.getenv("DEMO_JITTER_MS", "10"))
        time.sleep((base_ms + random.random() * jitter_ms) / 1000)
        return authorize_payment(request)


def create_server(max_workers: int = 10) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    payments_pb2_grpc.add_PaymentsServicer_to_server(PaymentsService(), server)
    return server


def serve() -> None:
    port = os.getenv("PORT", "8082")
    server = create_server()
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"grpc-payments-api listening on :{port}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
