from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import CarouselPhoto, Document


def schedule_file_cleanup(name, storage, using, model=Document, field="file"):
    def cleanup():
        if not model.objects.using(using).filter(**{field: name}).exists():
            storage.delete(name)

    transaction.on_commit(cleanup, using=using, robust=True)


@receiver(pre_save, sender=Document)
@receiver(pre_save, sender=CarouselPhoto)
def remember_replaced_file(sender, instance, using, update_fields=None, **kwargs):
    instance._replaced_file = None
    field = "image" if sender is CarouselPhoto else "file"
    if instance.pk and (update_fields is None or field in update_fields):
        old = sender.objects.using(using).filter(pk=instance.pk).first()
        old_file = getattr(old, field, None)
        new_file = getattr(instance, field)
        if old_file and (
            not new_file._committed or old_file.name != new_file.name
        ):
            instance._replaced_file = (old_file.name, old_file.storage, field)


@receiver(post_save, sender=Document)
@receiver(post_save, sender=CarouselPhoto)
def cleanup_replaced_file(sender, instance, using, **kwargs):
    if getattr(instance, "_replaced_file", None):
        name, storage, field = instance._replaced_file
        schedule_file_cleanup(name, storage, using, model=sender, field=field)
        instance._replaced_file = None


@receiver(post_delete, sender=Document)
@receiver(post_delete, sender=CarouselPhoto)
def cleanup_deleted_file(sender, instance, using, **kwargs):
    field = "image" if sender is CarouselPhoto else "file"
    file = getattr(instance, field)
    if file:
        schedule_file_cleanup(file.name, file.storage, using, model=sender, field=field)
