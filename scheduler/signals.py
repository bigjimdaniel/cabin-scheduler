from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Document


def schedule_file_cleanup(name, storage, using):
    def cleanup():
        if not Document.objects.using(using).filter(file=name).exists():
            storage.delete(name)

    transaction.on_commit(cleanup, using=using, robust=True)


@receiver(pre_save, sender=Document)
def remember_replaced_file(sender, instance, using, update_fields=None, **kwargs):
    instance._replaced_file = None
    if instance.pk and (update_fields is None or "file" in update_fields):
        old = sender.objects.using(using).filter(pk=instance.pk).first()
        if old and old.file and (
            not instance.file._committed or old.file.name != instance.file.name
        ):
            instance._replaced_file = (old.file.name, old.file.storage)


@receiver(post_save, sender=Document)
def cleanup_replaced_file(sender, instance, using, **kwargs):
    if getattr(instance, "_replaced_file", None):
        name, storage = instance._replaced_file
        schedule_file_cleanup(name, storage, using)
        instance._replaced_file = None


@receiver(post_delete, sender=Document)
def cleanup_deleted_file(sender, instance, using, **kwargs):
    if instance.file:
        schedule_file_cleanup(instance.file.name, instance.file.storage, using)
