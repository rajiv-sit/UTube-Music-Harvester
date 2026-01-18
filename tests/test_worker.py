from utube.gui import Worker, WorkerError


def test_worker_success() -> None:
    worker = Worker(lambda: 5)
    results = []
    worker.signals.finished.connect(lambda value: results.append(value))
    worker.run()
    assert results == [5]


def test_worker_error() -> None:
    def boom():
        raise RuntimeError("fail")

    worker = Worker(boom, context="unit")
    errors = []
    worker.signals.error.connect(lambda err: errors.append(err))
    worker.run()
    assert isinstance(errors[0], WorkerError)
    assert errors[0].context == "unit"
