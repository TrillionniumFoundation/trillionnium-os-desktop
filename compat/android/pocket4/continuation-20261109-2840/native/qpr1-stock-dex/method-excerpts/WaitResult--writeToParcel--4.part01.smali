.method public whitelist writeToParcel(Landroid/os/Parcel;I)V
    .registers 5
    .param p1, "dest"    # Landroid/os/Parcel;
    .param p2, "flags"    # I

    #@0
    .line 96
    iget v0, p0, Landroid/app/WaitResult;->result:I

    #@2
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@5
    .line 97
    iget-boolean v0, p0, Landroid/app/WaitResult;->timeout:Z

    #@7
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@a
    .line 98
    iget-object v0, p0, Landroid/app/WaitResult;->who:Landroid/content/ComponentName;

    #@c
    invoke-static {v0, p1}, Landroid/content/ComponentName;->writeToParcel(Landroid/content/ComponentName;Landroid/os/Parcel;)V

    #@f
    .line 99
    iget-wide v0, p0, Landroid/app/WaitResult;->totalTime:J

    #@11
    invoke-virtual {p1, v0, v1}, Landroid/os/Parcel;->writeLong(J)V

    #@14
    .line 100
    iget v0, p0, Landroid/app/WaitResult;->launchState:I

    #@16
    invoke-virtual {p1, v0}, Landroid/os/Parcel;->writeInt(I)V

    #@19
    .line 101
    return-void
.end method
