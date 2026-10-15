package com.cloudstreamid.layarkaca21provider

import android.content.Context
import com.lagradost.cloudstream3.plugins.CloudstreamPlugin
import com.lagradost.cloudstream3.plugins.Plugin

@CloudstreamPlugin
class LayarKaca21Plugin : Plugin() {
    override fun load(context: Context) {
        registerMainAPI(LayarKaca21Provider())
    }
}
